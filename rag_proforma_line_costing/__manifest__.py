{
    'name': 'Pro Forma Line-Item Costing',
    'version': '19.0.1.0.0',
    'category': 'Sales/Accounting',
    'summary': 'Track pro forma line costs and linked vendor bills or expenses',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'account',
        'hr_expense',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/hr_expense_views.xml',
        'views/proforma_linked_cost_views.xml',
        'views/intercompany_billing_rule_views.xml',
        'wizard/sale_partial_invoice_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
