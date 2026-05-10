from odoo import api, fields, models


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
