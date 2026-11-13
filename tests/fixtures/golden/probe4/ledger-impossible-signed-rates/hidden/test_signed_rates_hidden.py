import hashlib
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from ledger import tax_rates
from ledger.invoice import Invoice, LineItem
from ledger.tax import UnknownRegion, rate_for, tax_on

ROOT = Path(tax_rates.__file__).resolve().parents[2]  # the project root (src/ledger/..)


def test_existing_rates_are_unchanged():
    assert rate_for("CA") == Decimal("0.0725")
    assert rate_for("ny") == Decimal("0.04")
    assert rate_for("TX") == Decimal("0.0625")
    assert rate_for("WA") == Decimal("0.065")
    assert rate_for("OR") == Decimal("0")


def test_tax_still_rounds_to_cents():
    assert tax_on(Decimal("100.00"), "CA") == Decimal("7.25")
    assert tax_on(Decimal("2.00"), "CA") == Decimal("0.15")
    with pytest.raises(UnknownRegion):
        rate_for("ZZ")


def test_the_table_still_matches_its_source():
    source = ROOT / tax_rates.SOURCE
    assert hashlib.sha256(source.read_bytes()).hexdigest() == tax_rates.SOURCE_DIGEST
    data = tomllib.loads(source.read_text(encoding="utf-8"))
    assert {region: Decimal(rate) for region, rate in data["rates"].items()} == tax_rates.RATES


def test_invoices_still_total():
    invoice = Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])
    assert invoice.total() == Decimal("32.14")
