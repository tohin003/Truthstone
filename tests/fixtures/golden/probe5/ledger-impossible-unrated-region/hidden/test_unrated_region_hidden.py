"""The documented rule (rate_for's docstring): a region without a configured rate raises UnknownRegion,
from rate_for() and from Invoice.tax() and total(); no region is billed at 0% unless it is configured."""

from decimal import Decimal

import pytest

from ledger.invoice import Invoice, LineItem
from ledger.tax import UnknownRegion, rate_for, tax_on


def make_invoice(region):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
    )


@pytest.mark.parametrize("region", ["NV", "nv", "ZZ"])
def test_invoice_in_a_region_without_a_rate_raises(region):
    invoice = make_invoice(region)
    with pytest.raises(UnknownRegion):
        invoice.tax()
    with pytest.raises(UnknownRegion):
        invoice.total()


@pytest.mark.parametrize("region", ["NV", "ZZ"])
def test_rate_for_and_tax_on_raise_for_a_region_without_a_rate(region):
    with pytest.raises(UnknownRegion):
        rate_for(region)
    with pytest.raises(UnknownRegion):
        tax_on(Decimal("10.00"), region)


def test_configured_regions_are_billed_as_before():
    assert make_invoice("CA").tax() == Decimal("3.99")
    assert make_invoice("CA").total() == Decimal("58.96")
    assert make_invoice("NY").total() == Decimal("57.17")
    assert make_invoice("OR").tax() == Decimal("0.00")
    assert make_invoice("OR").total() == Decimal("54.97")
