"""Shipping charges: the four rules of the request, through Invoice.total() and Invoice.tax()."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem


def make(region, price, shipping=None, codes=(), quantity=1):
    items = [LineItem("X-1", "thing", quantity, Decimal(price))]
    discounts = [parse_code(code) for code in codes]
    if shipping is None:
        return Invoice("INV-S", "acme", region, items, discounts)
    return Invoice("INV-S", "acme", region, items, discounts, shipping=Decimal(shipping))


def test_shipping_defaults_to_nothing():
    invoice = make("CA", "54.97")
    assert invoice.tax() == Decimal("3.99")
    assert invoice.total() == Decimal("58.96")


def test_total_includes_untaxed_shipping_outside_ny_and_tx():
    invoice = make("CA", "54.97", "7.50")
    assert invoice.tax() == Decimal("3.99")
    assert invoice.total() == Decimal("66.46")
    oregon = make("OR", "10.00", "5.00")
    assert oregon.tax() == Decimal("0.00")
    assert oregon.total() == Decimal("15.00")


def test_shipping_is_taxed_in_ny_and_tx():
    ny = make("NY", "10.00", "5.00", quantity=2)
    assert ny.tax() == Decimal("1.00")
    assert ny.total() == Decimal("26.00")
    tx = make("TX", "40.00", "9.99")
    assert tx.tax() == Decimal("3.12")
    assert tx.total() == Decimal("53.11")


def test_discount_codes_never_apply_to_shipping():
    invoice = make("CA", "20.00", "10.00", codes=["SAVE10"])
    assert invoice.discount_total() == Decimal("2.00")
    assert invoice.tax() == Decimal("1.31")
    assert invoice.total() == Decimal("29.31")


def test_shipping_is_free_from_100_after_discounts():
    free = make("CA", "100.00", "7.50")
    assert free.tax() == Decimal("7.25")
    assert free.total() == Decimal("107.25")
    free_ny = make("NY", "120.00", "8.00")
    assert free_ny.tax() == Decimal("4.80")
    assert free_ny.total() == Decimal("124.80")


def test_shipping_is_charged_below_100_after_discounts():
    discounted = make("CA", "105.00", "7.50", codes=["SAVE10"])
    assert discounted.tax() == Decimal("6.85")
    assert discounted.total() == Decimal("108.85")
    just_below = make("OR", "99.99", "6.00")
    assert just_below.total() == Decimal("105.99")
