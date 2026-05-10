from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    incurred_cost = fields.Monetary(
        string='Incurred Cost',
        currency_field='currency_id',
        groups='account.group_account_invoice',
        help='Persisted cost copied from the sale order line as unit cost multiplied by the invoiced quantity.',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    proforma_sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Pro Forma',
        copy=False,
        index=True,
        domain="[('company_id', '=', company_id)]",
        groups='account.group_account_invoice',
        help='Sale order or pro forma this vendor bill/receipt cost belongs to.',
    )
    intercompany_vendor_bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Intercompany Vendor Bill',
        copy=False,
        readonly=True,
        groups='account.group_account_invoice',
    )
    intercompany_source_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Intercompany Source Invoice',
        copy=False,
        readonly=True,
        groups='account.group_account_invoice',
    )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        if not self.env.context.get('skip_proforma_linked_cost_sync'):
            moves._sync_proforma_linked_costs()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_proforma_linked_cost_sync'):
            return res
        sync_fields = {
            'proforma_sale_order_id',
            'amount_total',
            'currency_id',
            'move_type',
            'state',
            'name',
            'ref',
            'invoice_line_ids',
            'line_ids',
        }
        if sync_fields & set(vals):
            self._sync_proforma_linked_costs()
        return res

    def _sync_proforma_linked_costs(self):
        linked_cost_model = self.env['proforma.linked.cost'].sudo()
        for move in self.sudo():
            linked_cost = linked_cost_model.search([('account_move_id', '=', move.id)], limit=1)
            if move.proforma_sale_order_id and move.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                vals = {
                    'sale_order_id': move.proforma_sale_order_id.id,
                    'cost_type': 'vendor_bill',
                    'account_move_id': move.id,
                    'company_id': move.company_id.id,
                    'currency_id': move.currency_id.id,
                    'amount': move.amount_total,
                }
                if linked_cost:
                    linked_cost.with_context(skip_proforma_source_sync=True).write(vals)
                else:
                    linked_cost_model.with_context(skip_proforma_source_sync=True).create(vals)
            elif linked_cost and linked_cost.cost_type == 'vendor_bill':
                linked_cost.unlink()

    def action_view_intercompany_vendor_bill(self):
        self.ensure_one()
        return self._get_intercompany_move_action(self.intercompany_vendor_bill_id)

    def action_view_intercompany_source_invoice(self):
        self.ensure_one()
        return self._get_intercompany_move_action(self.intercompany_source_invoice_id)

    def _get_intercompany_move_action(self, move):
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_in_invoice_type')
        if move.move_type in ('out_invoice', 'out_refund', 'out_receipt'):
            action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        action['res_id'] = move.id
        action['context'] = {'default_move_type': move.move_type}
        return action

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get('skip_intercompany_vendor_bill'):
            posted._create_intercompany_vendor_bills()
        return posted

    def _create_intercompany_vendor_bills(self):
        rules = self.env['rag.intercompany.billing.rule'].sudo().search([('active', '=', True)])
        if not rules:
            return

        for invoice in self.filtered(lambda move: move.move_type == 'out_invoice' and move.state == 'posted'):
            if invoice.intercompany_vendor_bill_id:
                continue

            rule = rules.filtered(lambda candidate: (
                candidate.seller_company_id == invoice.company_id
                and candidate.buyer_company_id.partner_id.commercial_partner_id == invoice.commercial_partner_id
            ))[:1]
            if not rule:
                continue

            vendor_bill = invoice._prepare_intercompany_vendor_bill(rule)
            invoice.sudo().intercompany_vendor_bill_id = vendor_bill
            invoice.message_post(body=_(
                'Draft intercompany vendor bill created for %(company)s: %(bill)s',
                company=rule.buyer_company_id.display_name,
                bill=vendor_bill._get_html_link(),
            ))

    def _prepare_intercompany_vendor_bill(self, rule):
        self.ensure_one()
        buyer_company = rule.buyer_company_id
        seller_partner = self.company_id.partner_id.commercial_partner_id
        fpos = self.env['account.fiscal.position'].with_company(buyer_company)._get_fiscal_position(
            seller_partner.with_company(buyer_company)
        )
        purchase_journal = rule.purchase_journal_id or self.env['account.journal'].with_company(buyer_company).search([
            ('type', '=', 'purchase'),
            ('company_id', '=', buyer_company.id),
        ], limit=1)
        if not purchase_journal:
            raise UserError(_('No purchase journal was found for %s.', buyer_company.display_name))

        line_commands = []
        markup_factor = 1.0 + (rule.markup_percent / 100.0)
        for source_line in self.invoice_line_ids.filtered(
            lambda line: line.display_type not in ('line_section', 'line_subsection', 'line_note')
        ):
            product = source_line.product_id.with_company(buyer_company)
            account = (
                product._get_product_accounts()['expense']
                if product
                else buyer_company.expense_account_id
            )
            if fpos:
                account = fpos.map_account(account)
            if not account:
                raise UserError(_(
                    'No expense account was found for line %(line)s in company %(company)s.',
                    line=source_line.display_name,
                    company=buyer_company.display_name,
                ))

            taxes = (
                product.supplier_taxes_id._filter_taxes_by_company(buyer_company)
                if product
                else self.env['account.tax']
            )
            taxes = fpos.map_tax(taxes) if fpos else taxes
            line_commands.append(Command.create({
                'display_type': source_line.display_type or 'product',
                'sequence': source_line.sequence,
                'name': source_line.name,
                'product_id': source_line.product_id.id,
                'product_uom_id': source_line.product_uom_id.id,
                'quantity': source_line.quantity,
                'price_unit': source_line.price_unit * markup_factor,
                'discount': source_line.discount,
                'account_id': account.id,
                'tax_ids': [Command.set(taxes.ids)],
                'incurred_cost': source_line.incurred_cost,
            }))

        bill_vals = {
            'move_type': 'in_invoice',
            'company_id': buyer_company.id,
            'journal_id': purchase_journal.id,
            'partner_id': seller_partner.id,
            'invoice_date': self.invoice_date,
            'invoice_origin': self.name,
            'ref': self.name,
            'currency_id': self.currency_id.id,
            'fiscal_position_id': fpos.id,
            'invoice_line_ids': line_commands,
            'intercompany_source_invoice_id': self.id,
        }
        if not line_commands:
            raise UserError(_('No invoiceable product lines were found on %s.', self.display_name))

        return self.env['account.move'].with_company(buyer_company).sudo().with_context(
            default_move_type='in_invoice',
            skip_intercompany_vendor_bill=True,
        ).create(bill_vals)
