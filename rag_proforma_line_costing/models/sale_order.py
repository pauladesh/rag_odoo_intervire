from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    linked_cost_ids = fields.One2many(
        comodel_name='proforma.linked.cost',
        inverse_name='sale_order_id',
        string='Linked Costs',
        groups='account.group_account_invoice',
    )
    linked_cost_count = fields.Integer(
        string='Linked Cost Count',
        compute='_compute_linked_cost_count',
        groups='account.group_account_invoice',
    )

    @api.depends('linked_cost_ids')
    def _compute_linked_cost_count(self):
        for order in self:
            order.linked_cost_count = len(order.linked_cost_ids)

    def action_view_linked_costs(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'rag_proforma_line_costing.action_proforma_linked_cost'
        )
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {
            'default_sale_order_id': self.id,
            'default_company_id': self.company_id.id,
            'default_currency_id': self.currency_id.id,
        }
        action['display_name'] = _('Linked Costs')
        return action


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    cost_price = fields.Monetary(
        string='Cost Price',
        currency_field='currency_id',
        groups='account.group_account_invoice',
        help='Internal pro forma line-item cost visible to Accounting / Invoicing users only.',
    )
