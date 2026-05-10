from odoo import api, fields, models


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    proforma_sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Pro Forma',
        copy=False,
        index=True,
        domain="[('company_id', '=', company_id)]",
        groups='account.group_account_invoice',
        help='Sale order or pro forma this expense cost belongs to.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        expenses = super().create(vals_list)
        if not self.env.context.get('skip_proforma_linked_cost_sync'):
            expenses._sync_proforma_linked_costs()
        return expenses

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_proforma_linked_cost_sync'):
            return res
        if {'proforma_sale_order_id', 'total_amount_currency', 'currency_id', 'name', 'state'} & set(vals):
            self._sync_proforma_linked_costs()
        return res

    def _sync_proforma_linked_costs(self):
        linked_cost_model = self.env['proforma.linked.cost'].sudo()
        for expense in self.sudo():
            linked_cost = linked_cost_model.search([('expense_id', '=', expense.id)], limit=1)
            if expense.proforma_sale_order_id:
                vals = {
                    'sale_order_id': expense.proforma_sale_order_id.id,
                    'cost_type': 'expense',
                    'expense_id': expense.id,
                    'company_id': expense.company_id.id,
                    'currency_id': expense.currency_id.id,
                    'amount': expense.total_amount_currency,
                }
                if linked_cost:
                    linked_cost.with_context(skip_proforma_source_sync=True).write(vals)
                else:
                    linked_cost_model.with_context(skip_proforma_source_sync=True).create(vals)
            elif linked_cost and linked_cost.cost_type == 'expense':
                linked_cost.unlink()
