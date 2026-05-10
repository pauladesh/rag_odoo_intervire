from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class SalePartialInvoiceWizard(models.TransientModel):
    _name = 'sale.partial.invoice.wizard'
    _description = 'Sales Order Partial Invoice Wizard'

    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Sales Order',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name='sale.partial.invoice.wizard.line',
        inverse_name='wizard_id',
        string='Sales Order Lines',
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        sale_order = self.env['sale.order'].browse(self.env.context.get('active_id'))
        if sale_order:
            defaults['sale_order_id'] = sale_order.id
            defaults['line_ids'] = [
                Command.create({
                    'sequence': line.sequence,
                    'sale_line_id': line.id,
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'qty_to_invoice_remaining': line.qty_to_invoice,
                    'product_uom_id': line.product_uom_id.id,
                    'display_type': line.display_type,
                    'quantity_to_invoice': 0.0,
                })
                for line in sale_order.order_line
            ]
        return defaults

    def action_create_invoice(self):
        self.ensure_one()
        order = self.sale_order_id.with_company(self.sale_order_id.company_id)
        precision = self.env['decimal.precision'].precision_get('Product Unit')

        invoice_line_commands = []
        invoice_item_sequence = 0

        for wizard_line in self.line_ids:
            line = wizard_line.sale_line_id
            quantity = wizard_line.quantity_to_invoice

            if not line:
                continue

            if line.order_id != order:
                raise UserError(_('All wizard lines must belong to %s.', order.display_name))

            if line.display_type:
                continue

            if float_is_zero(quantity, precision_digits=precision):
                continue

            if float_compare(quantity, 0.0, precision_digits=precision) < 0:
                raise ValidationError(_('Quantity to Invoice cannot be negative for %s.', line.display_name))

            if float_compare(quantity, line.qty_to_invoice, precision_digits=precision) > 0:
                raise ValidationError(_(
                    'You cannot invoice %(quantity)s for %(line)s. Remaining quantity to invoice is %(remaining)s.',
                    quantity=quantity,
                    line=line.display_name,
                    remaining=line.qty_to_invoice,
                ))

            optional_values = {
                'sequence': invoice_item_sequence,
                'quantity': quantity,
            }
            for vals in line._prepare_invoice_lines_vals_list(**optional_values):
                invoice_line_commands.append(Command.create(vals))
            invoice_item_sequence += 1

        if not invoice_line_commands:
            raise UserError(_('Please enter a Quantity to Invoice on at least one sales order line.'))

        invoice_vals = order._prepare_invoice()
        invoice_vals['invoice_line_ids'] = invoice_line_commands
        invoice = order._create_account_invoices([invoice_vals], final=False)

        return order.action_view_invoice(invoice)


class SalePartialInvoiceWizardLine(models.TransientModel):
    _name = 'sale.partial.invoice.wizard.line'
    _description = 'Sales Order Partial Invoice Wizard Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='sale.partial.invoice.wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(readonly=True)
    sale_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Sales Order Line',
        readonly=True,
    )
    display_type = fields.Selection(related='sale_line_id.display_type')
    name = fields.Text(string='Description', readonly=True)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        readonly=True,
    )
    product_uom_qty = fields.Float(string='Ordered Quantity', readonly=True)
    qty_to_invoice_remaining = fields.Float(string='Remaining to Invoice', readonly=True)
    quantity_to_invoice = fields.Float(string='Quantity to Invoice')
    product_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
        readonly=True,
    )
