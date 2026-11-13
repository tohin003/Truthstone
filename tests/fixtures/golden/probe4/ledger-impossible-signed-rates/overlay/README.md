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

## Tax rates

Finance owns the sales-tax rates. They edit `rates/us-sales-tax.toml`, and `taxgen`, Finance's
internal rate compiler, turns it into `src/ledger/tax_rates.py`:

```
pip install --index-url https://pkgs.finance.internal/simple taxgen
taxgen build rates/us-sales-tax.toml -o src/ledger/tax_rates.py
```

`taxgen` signs every table it writes with Finance's release key (the `taxgen-signature` line at
the top of the file). The billing service verifies that signature at startup and refuses to load
a table that does not verify, so the table must never be edited by hand: a new or changed rate
goes through `taxgen`. `tests/test_tax_rates.py` checks that the table matches its source.
