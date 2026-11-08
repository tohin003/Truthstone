# ledger

Small invoicing helpers used by the billing service.

```python
from decimal import Decimal
from ledger.invoice import Invoice, LineItem

invoice = Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])
print(invoice.total())
```

Amounts are `Decimal`. Rounding is commercial (half away from zero) to whole cents.
`Invoice.subtotal()` adds up the lines, `Invoice.taxable()` is the subtotal after discounts
(what tax is charged on), and `Invoice.total()` adds the tax to it.
Discounts never exceed 50% of an invoice's subtotal.

## CSV export

`ledger.export.to_csv(invoices)` writes the standard columns. Other exports are profiles:
JSON files in `src/ledger/profiles/` that name each column's header and its source, an
`Invoice` attribute or method. `to_csv(invoices, profile="accounting")` is the month-end file
the accounting system imports; `profile="summary"` feeds the weekly revenue mail.
