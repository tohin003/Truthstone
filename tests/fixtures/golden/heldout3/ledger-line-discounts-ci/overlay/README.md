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

## Line discounts

The line export (`ledger.export.lines_to_csv`) gives accounting every invoice line with its
share of the invoice's discount. Accounting's import rejects an invoice whose line discounts do
not add up to its discount to the cent, so `Invoice.line_discounts()` allocates the shares like
this:

1. Only charge lines share the discount. A credit line (a negative amount) or a line of 0.00 gets
   0.00.
2. A charge line's exact share is discount x line amount / the sum of the charge lines.
3. Each line first gets its exact share rounded down to the cent.
4. The cents still missing go one each to the lines with the largest remainders (the part that
   was rounded away). Between equal remainders, the earlier line comes first.

So the shares are never negative and always add up to `discount_total()`. The tests in
`tests/test_line_discounts.py` are the worked examples accounting signed off.
