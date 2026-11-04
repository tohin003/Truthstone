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

## Reports

`ledger.reports` sums batches of invoices. Revenue always means what the customers pay: each
invoice's `total()`, after discounts and tax. `monthly_revenue(invoices, year, month)` is the
month-end report finance closes the books with: revenue per region from the invoices issued
in that calendar month, first day to last day. Drafts (no `issued_on`) are left out.

Tests that fail on main for a known reason are listed in `KNOWN_ISSUES.md`.
