from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem


def lines(*prices):
    return [LineItem(f"L-{i}", "line", 1, Decimal(price)) for i, price in enumerate(prices)]


def test_tax_is_rounded_once_on_the_invoice_subtotal():
    assert Invoice("INV-8", "acme", "CA", lines("1.00", "1.00")).tax() == Decimal("0.15")
    # three lines of 0.10 at 7.25%: 0.02175 on the subtotal -> 0.02 (per line it would be 0.03)
    assert Invoice("INV-9", "acme", "CA", lines("0.10", "0.10", "0.10")).tax() == Decimal("0.02")


def test_documented_invoice_totals_are_unchanged():
    invoice = Invoice(
        "INV-7", "acme", "CA",
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
    )
    assert invoice.tax() == Decimal("3.99")
    assert invoice.total() == Decimal("58.96")


def test_tax_applies_to_the_discounted_subtotal():
    invoice = Invoice(
        "INV-7", "acme", "CA",
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code("SAVE10")],
    )
    assert invoice.tax() == Decimal("3.59")
    assert invoice.total() == Decimal("53.06")
