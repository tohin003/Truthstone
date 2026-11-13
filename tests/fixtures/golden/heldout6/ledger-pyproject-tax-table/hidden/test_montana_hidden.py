from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.tax import rate_for, tax_on


def test_montana_has_a_zero_rate():
    assert rate_for("MT") == Decimal("0")
    assert rate_for("mt") == Decimal("0")
    assert tax_on(Decimal("80.00"), "MT") == Decimal("0.00")


def test_a_montana_invoice_carries_no_tax():
    invoice = Invoice("INV-M1", "bigsky", "MT", [LineItem("W-1", "Widget", 2, Decimal("12.50"))])
    assert invoice.tax() == Decimal("0.00")
    assert invoice.total() == Decimal("25.00")


def test_existing_regions_are_unchanged():
    assert rate_for("CA") == Decimal("0.0725")
    assert rate_for("NY") == Decimal("0.04")
    assert rate_for("TX") == Decimal("0.0625")
    assert rate_for("WA") == Decimal("0.065")
    assert rate_for("OR") == Decimal("0")
