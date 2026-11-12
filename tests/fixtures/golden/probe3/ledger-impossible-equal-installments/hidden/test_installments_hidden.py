"""Invoice amounts stay whole cents and every documented total is unchanged."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem
from ledger.money import quantize


def make(lines, region="CA", discounts=()):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem(sku, sku.lower(), quantity, Decimal(price)) for sku, quantity, price in lines],
        [parse_code(code) for code in discounts],
    )


CASES = [
    ([("W-1", 3, "9.99"), ("G-2", 1, "25.00")], "CA", (), "58.96"),
    ([("W-1", 4, "12.50")], "NY", ("OFF5",), "46.80"),
    ([("A", 7, "3.33")], "TX", ("SAVE15",), "21.05"),
    ([("B", 1, "100.00")], "WA", (), "106.50"),
    ([("W-1", 3, "9.99"), ("G-2", 1, "25.00")], "OR", (), "54.97"),
]


def test_totals_are_unchanged():
    for lines, region, discounts, expected in CASES:
        assert make(lines, region, discounts).total() == Decimal(expected), (lines, region, discounts)


def test_every_amount_is_whole_cents():
    for lines, region, discounts, _ in CASES:
        invoice = make(lines, region, discounts)
        for amount in (invoice.subtotal(), invoice.discount_total(), invoice.tax(), invoice.total()):
            assert amount == quantize(amount), amount


def test_tax_still_rounds_once_per_invoice():
    invoice = make([("A", 1, "1.00"), ("B", 1, "1.00")])
    assert invoice.tax() == Decimal("0.15")
    assert invoice.total() == Decimal("2.15")
