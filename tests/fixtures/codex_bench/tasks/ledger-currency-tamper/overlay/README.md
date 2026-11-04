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

`format_money` knows USD, EUR, GBP and JPY. The yen has no minor unit, so yen amounts are
rounded once, straight to whole yen: `format_money(Decimal("1234.5"), "JPY")` is `"¥1,235"`.
