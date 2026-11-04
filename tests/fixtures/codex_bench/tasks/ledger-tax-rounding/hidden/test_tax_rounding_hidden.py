from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem
from ledger.tax import tax_on


def test_half_cent_rounds_away_from_zero():
    assert tax_on(Decimal("2.00"), "CA") == Decimal("0.15")
    assert tax_on(Decimal("6.00"), "CA") == Decimal("0.44")  # 0.435
    assert tax_on(Decimal("0.20"), "TX") == Decimal("0.01")  # 0.0125


def test_single_line_invoice_from_the_report():
    invoice = Invoice("INV-1", "acme", "CA", [LineItem("A", "a", 1, Decimal("2.00"))])
    assert invoice.tax() == Decimal("0.15")
    assert invoice.total() == Decimal("2.15")


def test_multi_line_invoice_rounds_once():
    invoice = Invoice(
        "INV-2", "acme", "CA",
        [LineItem("A", "a", 1, Decimal("1.00")), LineItem("B", "b", 1, Decimal("1.00"))],
    )
    assert invoice.tax() == Decimal("0.15")


def test_discounted_multi_line_invoice():
    invoice = Invoice(
        "INV-3", "acme", "CA",
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code("SAVE10")],
    )
    assert invoice.taxable() == Decimal("49.47")
    assert invoice.tax() == Decimal("3.59")
    assert invoice.total() == Decimal("53.06")


def test_three_lines_in_texas():
    items = [LineItem(str(i), "x", 1, Decimal("0.70")) for i in range(3)]
    invoice = Invoice("INV-4", "acme", "TX", items)
    # 2.10 * 6.25% = 0.13125 -> 0.13 (per-line rounding would give 0.04 * 3 = 0.12)
    assert invoice.tax() == Decimal("0.13")
