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

## Settings

`ledger.toml` at the project root holds the billing service's settings:

| key | default | what it does |
|---|---|---|
| `[export] delimiter` | `","` | column separator of `export.to_csv()` |
| `[reports] top_customers` | `3` | how many customers `reports.top_customers()` lists when not told |

A missing file, section or key means the default.
