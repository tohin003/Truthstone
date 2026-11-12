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

Discounts and tax are worked out on the invoice as a whole: `discount_total()` applies the
codes to the subtotal and rounds once, and `tax()` rounds once on the discounted subtotal. The
filed invoices (and accounting's reconciliation) depend on these numbers, so they never change
for an existing invoice.
