from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProformaLinkedCost(models.Model):
    _name = 'proforma.linked.cost'
    _description = 'Pro Forma Linked Cost'
    _order = 'date desc, id desc'
    _check_company_auto = True
    _sql_constraints = [
        (
            'unique_account_move_cost',
            'unique(account_move_id)',
            'A vendor bill can only be linked to one pro forma cost record.',
        ),
        (
            'unique_expense_cost',
            'unique(expense_id)',
            'An expense can only be linked to one pro forma cost record.',
        ),
    ]

    name = fields.Char(string='Description', compute='_compute_name', store=True, readonly=False)
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Pro Forma',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    cost_type = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('vendor_bill', 'Vendor Bill'),
            ('expense', 'Expense'),
        ],
        string='Type',
        required=True,
        default='manual',
    )
    account_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        domain="[('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    expense_id = fields.Many2one(
        comodel_name='hr.expense',
        string='Expense',
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    date = fields.Date(default=fields.Date.context_today)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(currency_field='currency_id', required=True)
    note = fields.Text()

    @api.depends('cost_type', 'account_move_id', 'expense_id', 'note')
    def _compute_name(self):
        for cost in self:
            if cost.account_move_id:
                cost.name = cost.account_move_id.display_name
            elif cost.expense_id:
                cost.name = cost.expense_id.display_name
            elif cost.note:
                cost.name = cost.note.splitlines()[0][:80]
            else:
                cost.name = dict(self._fields['cost_type'].selection).get(cost.cost_type)

    @api.constrains('cost_type', 'account_move_id', 'expense_id')
    def _check_linked_document(self):
        for cost in self:
            if cost.cost_type == 'vendor_bill' and not cost.account_move_id:
                raise ValidationError('A vendor bill linked cost must reference a vendor bill.')
            if cost.cost_type == 'expense' and not cost.expense_id:
                raise ValidationError('An expense linked cost must reference an expense.')

    @api.onchange('account_move_id')
    def _onchange_account_move_id(self):
        for cost in self:
            if cost.account_move_id:
                cost.cost_type = 'vendor_bill'
                cost.company_id = cost.account_move_id.company_id
                cost.currency_id = cost.account_move_id.currency_id
                cost.amount = cost.account_move_id.amount_total

    @api.onchange('expense_id')
    def _onchange_expense_id(self):
        for cost in self:
            if cost.expense_id:
                cost.cost_type = 'expense'
                cost.company_id = cost.expense_id.company_id
                cost.currency_id = cost.expense_id.currency_id
                cost.amount = cost.expense_id.total_amount_currency

    @api.model_create_multi
    def create(self, vals_list):
        costs = super().create(vals_list)
        if not self.env.context.get('skip_proforma_source_sync'):
            costs._sync_source_documents()
        return costs

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get('skip_proforma_source_sync')
            and {'sale_order_id', 'cost_type', 'account_move_id', 'expense_id'} & set(vals)
        ):
            self._sync_source_documents()
        return res

    def unlink(self):
        moves = self.sudo().mapped('account_move_id')
        expenses = self.sudo().mapped('expense_id')
        res = super().unlink()
        moves.filtered('proforma_sale_order_id').sudo().with_context(
            skip_proforma_linked_cost_sync=True
        ).write({'proforma_sale_order_id': False})
        expenses.filtered('proforma_sale_order_id').sudo().with_context(
            skip_proforma_linked_cost_sync=True
        ).write({'proforma_sale_order_id': False})
        return res

    def _sync_source_documents(self):
        for cost in self.sudo():
            if cost.cost_type == 'vendor_bill' and cost.account_move_id:
                cost.account_move_id.with_context(
                    skip_proforma_linked_cost_sync=True
                ).write({'proforma_sale_order_id': cost.sale_order_id.id})
            elif cost.cost_type == 'expense' and cost.expense_id:
                cost.expense_id.with_context(
                    skip_proforma_linked_cost_sync=True
                ).write({'proforma_sale_order_id': cost.sale_order_id.id})
