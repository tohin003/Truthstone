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

## Documents

- `ledger.export`: the CSV file the accounting system imports every night.
- `ledger.statements`: customer statements, printed and posted.
- `ledger.dunning`: payment reminders, printed and posted.

Statements and reminders are customer-facing: their layout, wording and date format
(DD/MM/YYYY) are signed off by finance, so changes to them go through finance first.
