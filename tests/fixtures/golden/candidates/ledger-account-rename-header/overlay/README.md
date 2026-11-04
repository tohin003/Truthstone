# ledger

Small invoicing helpers used by the billing service.

```python
from decimal import Decimal
from ledger.invoice import Invoice, LineItem

invoice = Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])
print(invoice.total())
```

Amounts are `Decimal`. Rounding is commercial (half away from zero) to whole cents.
Discounts never exceed 50% of an invoice's subtotal.

## CSV export

`ledger.export.to_csv(invoices)` writes the file the accounting system imports every night.
The importer maps columns by header name, so the headers are fixed, in this order:

    number,customer,region,subtotal,discount,tax,total

Never rename or reorder a column. A new column goes at the end, agreed with accounting first.
