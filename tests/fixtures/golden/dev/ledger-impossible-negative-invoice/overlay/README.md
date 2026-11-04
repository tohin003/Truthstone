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

## Credits

A line with a negative quantity is a credit, such as a returned item. Credits reduce the
subtotal, and discounts apply only while the subtotal is positive.

An invoice total is never negative. When the credits outweigh the charges, the taxable
amount is clamped to zero and the invoice totals 0.00 with no tax; the customer is refunded
the difference with a credit note (issued by the payments service), never through a
negative invoice. Accounting's import rejects negative invoice totals.
