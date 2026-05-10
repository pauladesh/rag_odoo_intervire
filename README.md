# Pro Forma Line Costing

Custom Odoo 19 Community module for pro forma line costing, linked cost tracking, partial invoicing, invoice-line cost persistence, and intercompany billing.

## Module

Technical name: `rag_proforma_line_costing`

Location:

```text
/opt/odoo/server_v19/custom_v19/rag_proforma_line_costing
```

Dependencies:

- `sale`
- `account`
- `hr_expense`

## Task A: Pro Forma Line-Item Costing

### Sale Order Line Cost

Adds `cost_price` on `sale.order.line`.

The field is monetary and uses the sale order line currency.

Security:

- Restricted at ORM level with `account.group_account_invoice`.
- Visible only to Accounting / Invoicing users.
- Added to Sales Order line form/list views and standalone Sales Order Line views.

### Linked Costs

Adds a `proforma.linked.cost` model to track costs linked to a Sales Order / Pro Forma.

Supported linked cost types:

- Manual
- Vendor Bill
- Expense

Sales Orders include:

- Linked Costs smart button.
- Linked Costs tab.

Vendor Bills and Expenses include a `Pro Forma` field. When populated, the module creates or updates a linked cost record automatically.

## Task B: Partial Invoicing Wizard

Adds a Sales Order button:

```text
Create Partial Invoice
```

The wizard:

- Lists all Sales Order lines.
- Shows ordered quantity and remaining quantity to invoice.
- Lets the user enter `Quantity to Invoice`.
- Validates that the entered quantity is not negative.
- Validates that the entered quantity does not exceed `qty_to_invoice`.
- Creates a draft customer invoice containing only the selected quantities.

The wizard uses Odoo's native invoice preparation flow so invoice lines remain linked to their source sale lines.

## Task C: Line-Level Margin Persistence

Adds `incurred_cost` on `account.move.line`.

When a sale order line is invoiced, the module carries the cost from:

```text
sale.order.line.cost_price
```

to:

```text
account.move.line.incurred_cost
```

### Partial Quantity Logic

`cost_price` is treated as a unit cost, similar to Odoo's `price_unit`.

Formula:

```text
incurred_cost = cost_price * invoiced_quantity
```

Example:

- Sale order line quantity: `10`
- Cost price: `100`
- Partial invoice quantity: `5`
- Invoice line incurred cost: `500`

This is proportional because the invoice line represents only the quantity actually invoiced. Margin reporting should compare revenue and cost for the same invoiced quantity, not the full sale order quantity.

## Task D: Regulatory Intercompany Billing

Adds Intercompany Billing Rules under:

```text
Accounting > Configuration > Intercompany Billing Rules
```

Rule fields:

- Seller Company
- Buyer Company
- Markup (%)
- Buyer Purchase Journal
- Active

Default markup is `10%`.

### Automatic Vendor Bill Creation

When Company A validates/posts a Customer Invoice:

1. The module checks for an active intercompany rule.
2. The rule must match:
   - Seller Company = invoice company.
   - Buyer Company partner = invoice customer.
3. The module creates a draft Vendor Bill in Company B.
4. Vendor Bill line price is calculated as:

```text
Company A invoice price + markup
```

Formula:

```text
vendor_bill_price_unit = source_invoice_price_unit * (1 + markup_percent / 100)
```

Example with 10% markup:

- Company A invoice line price: `100`
- Company B vendor bill line price: `110`

### Fiscal Position and Tax Mapping

The vendor bill is created in the Buyer Company's accounting context.

Tax handling:

- Purchase taxes are taken from the product in Company B.
- The fiscal position is resolved for Company A's partner in Company B.
- Taxes are mapped using the fiscal position before being applied to the vendor bill.

This ensures the generated Vendor Bill follows the Buyer Company's fiscal position and tax mapping.

### Traceability

The source Customer Invoice stores a link to the generated intercompany Vendor Bill.

The generated Vendor Bill stores a link back to the source Customer Invoice.

Smart buttons allow navigation between both documents.

## Setup

1. Upgrade the module:

```bash
./odoo-bin -c odoo_comm.conf -u rag_proforma_line_costing -d <database_name>
```

2. Ensure users who need costing access have Accounting / Invoicing rights.

3. Configure intercompany rules if Task D is required:

```text
Accounting > Configuration > Intercompany Billing Rules
```

4. Ensure Buyer Company has:

- Purchase journal.
- Expense accounts configured.
- Purchase taxes configured on products.
- Fiscal positions configured where required.

## Important Notes

- Generated intercompany Vendor Bills are left in Draft state.
- The module avoids creating duplicate intercompany bills by storing the generated bill on the source invoice.
- `cost_price` and `incurred_cost` are restricted to Accounting / Invoicing users.
- A module upgrade is required after installation or after code updates that add fields/models.
