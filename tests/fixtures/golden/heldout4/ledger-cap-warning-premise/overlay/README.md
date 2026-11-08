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

## The nightly export

`deploy/nightly_export.py` runs every night on the billing host: it reads the day's invoices
(a JSON dump from the billing service), writes the CSV that accounting imports, and its stderr
is mailed to billing in the morning. What reaches that mail is set in `deploy/logging.ini`.

```
PYTHONPATH=src python deploy/nightly_export.py invoices.json export.csv
```
