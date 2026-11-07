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

## Amounts on invoices, by locale

`ledger.money.format_money(amount, currency="USD", locale="en-US")` writes an amount the way the
customer's locale does. The amount is rounded to whole cents first (half away from zero). The
currency gives the symbol (USD `$`, EUR `€`, GBP `£`); the locale gives the separators, the digit
grouping and where the symbol goes:

| locale  | decimal | thousands separator                      | symbol                                 | 1234.5 EUR    | -5 EUR    |
| ------- | ------- | ---------------------------------------- | -------------------------------------- | ------------- | --------- |
| `en-US` | `.`     | `,` every three digits                   | before, no space                       | `€1,234.50`   | `-€5.00`  |
| `en-GB` | `.`     | `,` every three digits                   | before, no space                       | `€1,234.50`   | `-€5.00`  |
| `de-DE` | `,`     | `.` every three digits                   | after one no-break space (U+00A0)      | `1.234,50 €`  | `-5,00 €` |
| `fr-FR` | `,`     | narrow no-break space (U+202F), every three | after one no-break space (U+00A0)   | `1 234,50 €`  | `-5,00 €` |
| `en-IN` | `.`     | `,` after the last three digits, then every two (`12,34,567.00`) | before, no space | `€1,234.50`   | `-€5.00`  |

The minus sign always comes first. An unknown locale raises `MoneyError`. These are the forms of
the CLDR data and of accounting's PDF renderer; `tests/test_money_locales.py` holds the examples
the invoice templates were checked against.
