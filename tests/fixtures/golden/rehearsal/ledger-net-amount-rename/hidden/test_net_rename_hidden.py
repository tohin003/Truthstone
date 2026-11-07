"""Invoice.taxable() is Invoice.net() now, everywhere it is used, and the old name is gone."""

from decimal import Decimal
from pathlib import Path

from ledger.discounts import parse_code
from ledger.export import load_profile, to_csv, to_row
from ledger.invoice import Invoice, LineItem

ROOT = Path(__file__).resolve().parents[2]


def invoices():
    return [
        Invoice(
            "INV-7",
            "acme",
            "CA",
            [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
            [parse_code("SAVE10")],
        ),
        Invoice("INV-8", "initech", "OR", [LineItem("A", "a", 2, Decimal("12.50"))]),
        Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))], [parse_code("OFF5")]),
    ]


def test_net_is_the_discounted_subtotal():
    a, b, c = invoices()
    assert a.net() == Decimal("49.47")
    assert b.net() == Decimal("25.00")
    assert c.net() == Decimal("15.00")


def test_the_old_name_is_gone():
    assert not hasattr(Invoice, "taxable")
    assert not hasattr(invoices()[0], "taxable")


def test_tax_and_totals_are_unchanged():
    a, b, c = invoices()
    assert (a.tax(), a.total()) == (Decimal("3.59"), Decimal("53.06"))
    assert (b.tax(), b.total()) == (Decimal("0.00"), Decimal("25.00"))
    assert (c.tax(), c.total()) == (Decimal("0.60"), Decimal("15.60"))


def test_the_accounting_export_still_works():
    assert to_csv(invoices(), profile="accounting").splitlines() == [
        "invoice,customer,net,tax,gross",
        "INV-7,acme,49.47,3.59,53.06",
        "INV-8,initech,25.00,0.00,25.00",
        "INV-9,globex,15.00,0.60,15.60",
    ]


def test_every_profile_still_exports():
    profiles = sorted((ROOT / "src" / "ledger" / "profiles").glob("*.json"))
    assert {path.stem for path in profiles} >= {"accounting", "summary"}
    for path in profiles:
        columns = load_profile(path.stem)
        for invoice in invoices():
            assert len(to_row(invoice, columns)) == len(columns), path.name


def test_the_standard_export_is_unchanged():
    assert to_csv(invoices()[:1]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-7,acme,CA,54.97,5.50,3.59,53.06",
    ]
