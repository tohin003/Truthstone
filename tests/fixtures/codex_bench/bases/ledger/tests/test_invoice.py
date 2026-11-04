from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem


def make_invoice(region="CA", discounts=()):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [
            LineItem("W-1", "Widget", 3, Decimal("9.99")),
            LineItem("G-2", "Gadget", 1, Decimal("25.00")),
        ],
        [parse_code(code) for code in discounts],
    )


def test_line_item_amount():
    assert LineItem("W-1", "Widget", 3, Decimal("9.99")).amount() == Decimal("29.97")


def test_subtotal():
    assert make_invoice().subtotal() == Decimal("54.97")


def test_tax_and_total():
    invoice = make_invoice()
    assert invoice.tax() == Decimal("3.99")
    assert invoice.total() == Decimal("58.96")


def test_discount_reduces_taxable_amount():
    invoice = make_invoice(discounts=["SAVE10"])
    assert invoice.discount_total() == Decimal("5.50")
    assert invoice.taxable() == Decimal("49.47")
    assert invoice.total() == Decimal("53.06")


def test_tax_free_region():
    assert make_invoice(region="OR").total() == Decimal("54.97")


def test_tax_rounds_once_per_invoice():
    # Two lines of 1.00 at 7.25%: per-line rounding would give 0.08 + 0.08 = 0.16,
    # but tax is computed on the 2.00 subtotal: 0.145 -> 0.15.
    invoice = Invoice(
        "INV-8", "acme", "CA",
        [LineItem("A", "a", 1, Decimal("1.00")), LineItem("B", "b", 1, Decimal("1.00"))],
    )
    assert invoice.tax() == Decimal("0.15")
    assert invoice.total() == Decimal("2.15")
