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

## Discount codes

`SAVE<n>` takes n percent off and `OFF<n>` takes n currency units off. Percentage codes apply
first, each to what is left after the ones before it, then fixed ones. The invoice's discount
is rounded once, to whole cents, and capped at 50% of the subtotal.

## Issued invoices

Once an invoice is issued its figures are final: accounting files them. A change to how
amounts are computed must leave the subtotal, discount, tax and total of every issued invoice
exactly as they were. `tests/test_fy2025_replay.py` replays the filed FY2025 year to check it.

## Development

    python -m pytest

runs every test. It takes about a minute, almost all of it `tests/test_fy2025_replay.py`;
see CONTRIBUTING.md.
