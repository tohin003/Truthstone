"""Nevada is a tax region at 6.85%; every other rate and rule is as before."""

from decimal import Decimal

import pytest

from ledger.discounts import parse_code
from ledger.export import to_row
from ledger.invoice import Invoice, LineItem
from ledger.tax import RATES, UnknownRegion, rate_for, tax_on


def test_nevada_is_taxed_at_6_85_percent():
    assert rate_for("NV") == Decimal("0.0685")
    assert rate_for("nv") == Decimal("0.0685")


def test_tax_on_nevada_amounts_rounds_to_cents():
    assert tax_on(Decimal("100.00"), "NV") == Decimal("6.85")
    assert tax_on(Decimal("19.99"), "NV") == Decimal("1.37")  # 1.369315
    assert tax_on(Decimal("2.00"), "NV") == Decimal("0.14")  # 0.137


def test_a_nevada_invoice():
    invoice = Invoice(
        "INV-NV-1",
        "acme",
        "NV",
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code("SAVE10")],
    )
    assert invoice.taxable() == Decimal("49.47")
    assert invoice.tax() == Decimal("3.39")  # 49.47 x 6.85% = 3.388695
    assert invoice.total() == Decimal("52.86")
    assert to_row(invoice)["tax"] == "3.39"


def test_the_other_rates_are_unchanged():
    assert {region: RATES[region] for region in ("CA", "NY", "TX", "WA", "OR")} == {
        "CA": Decimal("0.0725"),
        "NY": Decimal("0.04"),
        "TX": Decimal("0.0625"),
        "WA": Decimal("0.065"),
        "OR": Decimal("0"),
    }
    assert set(RATES) == {"CA", "NY", "TX", "WA", "OR", "NV"}


def test_unknown_regions_still_raise():
    with pytest.raises(UnknownRegion):
        rate_for("NM")
