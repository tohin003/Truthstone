from decimal import Decimal

import pytest

from ledger.tax import UnknownRegion, rate_for, tax_on


def test_rates():
    assert rate_for("ca") == Decimal("0.0725")
    assert rate_for("OR") == Decimal("0")


def test_unknown_region():
    with pytest.raises(UnknownRegion):
        rate_for("ZZ")


def test_tax_on_rounds_to_cents():
    assert tax_on(Decimal("100.00"), "CA") == Decimal("7.25")
    assert tax_on(Decimal("19.99"), "NY") == Decimal("0.80")


def test_tax_on_half_cent_rounds_up():
    # 2.00 * 7.25% = 0.145 exactly: commercial rounding takes it to 0.15.
    assert tax_on(Decimal("2.00"), "CA") == Decimal("0.15")
