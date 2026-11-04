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

`ledger.export.to_csv` writes the file the nightly job uploads to the ERP, in the ERP's
import format v1.9: `number,customer,subtotal,discount,tax,total`, LF line endings, amounts
with two decimals. The ERP's parser matches that layout exactly, byte for byte, so the
format is frozen: a new column, a renamed header or different number formatting needs a
coordinated ERP release (the next one is planned for Q1). `tests/golden/export_v19.csv`
pins the exact bytes.
