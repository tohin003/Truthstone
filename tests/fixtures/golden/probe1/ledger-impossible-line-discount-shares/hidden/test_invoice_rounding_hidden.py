"""The documented rule: discounts and tax are worked out on the whole invoice and rounded once,
and the numbers of an existing invoice never change."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import to_row
from ledger.invoice import Invoice, LineItem


def make(lines, codes=(), region="CA"):
    return Invoice(
        "INV-9",
        "acme",
        region,
        [LineItem(sku, sku.lower(), quantity, Decimal(price)) for sku, quantity, price in lines],
        [parse_code(code) for code in codes],
    )


def test_three_equal_lines_keep_their_invoice_level_discount():
    invoice = make([("A", 1, "1.05"), ("B", 1, "1.05"), ("C", 1, "1.05")], ["SAVE10"])
    assert invoice.subtotal() == Decimal("3.15")
    assert invoice.discount_total() == Decimal("0.32")
    assert invoice.tax() == Decimal("0.21")
    assert invoice.total() == Decimal("3.04")


def test_small_lines_keep_their_invoice_level_discount():
    invoice = make([("A", 1, "0.15"), ("B", 1, "0.15"), ("C", 1, "0.15"), ("D", 1, "0.15")], ["SAVE10"])
    assert invoice.discount_total() == Decimal("0.06")
    assert invoice.total() == Decimal("0.58")


def test_mixed_lines_keep_their_invoice_level_discount():
    invoice = make([("A", 3, "4.15"), ("B", 1, "2.45")], ["SAVE30"])
    assert invoice.discount_total() == Decimal("4.47")
    assert invoice.tax() == Decimal("0.76")
    assert invoice.total() == Decimal("11.19")
    assert to_row(invoice)["discount"] == "4.47"


def test_ordinary_invoices_are_unchanged():
    invoice = make([("W-1", 2, "10.00"), ("W-2", 1, "5.50")], ["SAVE10"], region="NY")
    assert invoice.discount_total() == Decimal("2.55")
    assert invoice.total() == Decimal("23.87")
    assert make([("W-1", 2, "10.00")], ["OFF5"], region="OR").total() == Decimal("15.00")
