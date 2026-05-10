from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RagIntercompanyBillingRule(models.Model):
    _name = 'rag.intercompany.billing.rule'
    _description = 'Intercompany Billing Rule'
    _order = 'seller_company_id, buyer_company_id'

    name = fields.Char(compute='_compute_name', store=True)
    active = fields.Boolean(default=True)
    seller_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Seller Company',
        required=True,
    )
    buyer_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Buyer Company',
        required=True,
    )
    markup_percent = fields.Float(
        string='Markup (%)',
        required=True,
        default=10.0,
        help='Percentage added to the seller invoice unit price when creating the buyer vendor bill.',
    )
    purchase_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Buyer Purchase Journal',
        domain="[('type', '=', 'purchase'), ('company_id', '=', buyer_company_id)]",
        help='Optional purchase journal to use on the generated buyer vendor bill.',
    )

    _sql_constraints = [
        (
            'unique_intercompany_pair',
            'unique(seller_company_id, buyer_company_id)',
            'Only one intercompany billing rule is allowed for the same seller and buyer company pair.',
        ),
    ]

    @api.depends('seller_company_id', 'buyer_company_id', 'markup_percent')
    def _compute_name(self):
        for rule in self:
            if rule.seller_company_id and rule.buyer_company_id:
                rule.name = '%s -> %s (%.2f%%)' % (
                    rule.seller_company_id.display_name,
                    rule.buyer_company_id.display_name,
                    rule.markup_percent,
                )
            else:
                rule.name = 'Intercompany Billing Rule'

    @api.constrains('seller_company_id', 'buyer_company_id')
    def _check_companies(self):
        for rule in self:
            if rule.seller_company_id == rule.buyer_company_id:
                raise ValidationError('Seller Company and Buyer Company must be different.')
