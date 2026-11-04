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

## Local setup

Copy `.env.example` to `.env` and fill in your ERP token. The billing service's local
database lives in `data/ledger.sqlite`. Both are gitignored and live only on your machine.

## Development

    pip install -e .
    pytest
    coverage run -m pytest && coverage html   # report in htmlcov/
    python -m build                           # wheel and sdist in dist/
