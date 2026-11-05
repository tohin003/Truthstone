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

## Statements

    PYTHONPATH=src python -m ledger.statements 2026-10

writes that month's statement for every customer to `statements/<customer>-<YYYY>-<MM>.txt`, from
`data/invoices.json`. The statements are mailed to customers at the start of the next month.
`statements/` is the record of what was sent (accounting sometimes corrects a statement by hand
before it goes out); it holds customer data, so it is not in git.
