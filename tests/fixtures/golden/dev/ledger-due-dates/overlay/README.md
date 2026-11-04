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

## Due dates

An invoice is due `terms_days` days after its `issued_on` date (30 unless the customer
has other terms). The bank does not collect at weekends, so a due date that falls on a
Saturday or a Sunday moves to the following Monday.

An unpaid invoice is overdue from the day *after* its due date: on the due date itself it
is not overdue yet. A paid invoice is never overdue.

- `Invoice.due_date()` returns the due date.
- `Invoice.is_overdue(today=None)` says whether the invoice is overdue on `today`, which
  defaults to the current date.

## Development

    pip install -e '.[test]'
    pytest

The `test` extra installs pytest and freezegun (used to pin "today" in the due-date tests).
