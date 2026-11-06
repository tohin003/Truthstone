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

## Subscriptions

A subscription renews every `every` months (1, 2, 3, 6 or 12) on its *anchor day*: the
day of the month it started. When a month has no such day, the subscription renews on
that month's last day, and the renewal after that is back on the anchor day. A monthly
subscription started on 31 January 2026 renews on 28 February, 31 March, 30 April and
31 May; one started on 29 February 2028 with yearly renewals renews on 28 February 2029,
2030 and 2031, then on 29 February 2032.

```python
from datetime import date
from ledger.periods import renewal_dates

renewal_dates(date(2026, 1, 10), 3)            # 10 February, 10 March, 10 April
renewal_dates(date(2026, 3, 5), 2, every=12)   # 5 March 2027, 5 March 2028
```

## Development

    pytest                 # the unit tests
    pytest -m calendar     # the calendar sweep

The calendar sweep (`tests/test_calendar_sweep.py`) checks `ledger.periods` against every
start date from 1900 to 2199, every plan length and two years of renewals. It takes about
ten seconds, so `pyproject.toml` leaves it out of the default run; run it whenever you
change anything in `ledger.periods`.
