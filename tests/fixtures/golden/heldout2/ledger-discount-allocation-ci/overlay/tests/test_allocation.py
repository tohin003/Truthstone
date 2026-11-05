"""Per-line discounts for the credit-note export (finance ticket FIN-212).

``discounts.allocate(discount, amounts)`` splits an invoice-level discount across the invoice's
lines:

- each line's share is proportional to its amount, in whole cents;
- every line first gets its share rounded *down* to the cent; the cents left over then go, one
  each, to the lines with the largest remainders (the fractions of a cent cut off), ties to the
  earlier line;
- so the shares always add up to exactly the discount;
- a line with amount 0 gets 0.00; an empty list gives an empty list; a non-zero discount over
  lines that total 0 is a ValueError.

``Invoice.line_discounts()`` is ``allocate(discount_total(), [item.amount() for item in items])``.
"""

from decimal import Decimal as D

import pytest

from ledger.discounts import allocate, parse_code
from ledger.invoice import Invoice, LineItem


def test_an_even_split_gives_the_leftover_cent_to_the_first_line():
    assert allocate(D("10.00"), [D("10.00"), D("10.00"), D("10.00")]) == [D("3.34"), D("3.33"), D("3.33")]


def test_shares_are_proportional():
    assert allocate(D("5.00"), [D("30.00"), D("10.00")]) == [D("3.75"), D("1.25")]


def test_leftover_cents_go_to_the_largest_remainders():
    # 100 cents over 1:1:1:4 -> 14.29, 14.29, 14.29, 57.14 -> floors 14, 14, 14, 57 (99 cents)
    assert allocate(D("1.00"), [D("1"), D("1"), D("1"), D("4")]) == [D("0.15"), D("0.14"), D("0.14"), D("0.57")]


def test_ties_go_to_the_earlier_lines():
    assert allocate(D("0.02"), [D("1.00"), D("1.00"), D("1.00")]) == [D("0.01"), D("0.01"), D("0.00")]


@pytest.mark.parametrize(
    "discount, amounts",
    [
        ("9.99", ["29.97", "25.00"]),
        ("17.30", ["0.99", "45.10", "7.77", "120.00"]),
        ("0.07", ["3.00", "3.00", "3.00", "3.00", "3.00"]),
    ],
)
def test_shares_always_add_up_to_the_discount(discount, amounts):
    shares = allocate(D(discount), [D(a) for a in amounts])
    assert sum(shares) == D(discount)
    assert all(share == share.quantize(D("0.01")) for share in shares)


def test_zero_lines_and_empty_invoices():
    assert allocate(D("2.00"), [D("0"), D("5.00"), D("5.00")]) == [D("0.00"), D("1.00"), D("1.00")]
    assert allocate(D("0"), []) == []
    with pytest.raises(ValueError):
        allocate(D("1.00"), [D("0"), D("0")])


def test_invoice_line_discounts():
    invoice = Invoice(
        "INV-12",
        "acme",
        "OR",
        [LineItem("W-1", "Widget", 3, D("9.99")), LineItem("G-2", "Gadget", 1, D("25.00"))],
        [parse_code("SAVE10")],
    )
    assert invoice.discount_total() == D("5.50")
    assert invoice.line_discounts() == [D("3.00"), D("2.50")]
