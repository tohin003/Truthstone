"""After the cleanup the package still imports and behaves exactly as before."""

from decimal import Decimal

from ledger.discounts import apply, parse_code
from ledger.export import COLUMNS, to_csv
from ledger.invoice import Invoice, LineItem
from ledger.money import format_money
from ledger.reports import average_invoice, revenue_by_region, top_customers
from ledger.tax import tax_on


def make_invoice(region="CA", discounts=()):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code(code) for code in discounts],
    )


def test_invoice_totals():
    assert make_invoice().total() == Decimal("58.96")
    assert make_invoice(discounts=["SAVE10"]).total() == Decimal("53.06")
    assert make_invoice(region="OR").total() == Decimal("54.97")


def test_csv_export():
    assert [header for header, _ in COLUMNS] == [
        "number", "customer", "region", "subtotal", "discount", "tax", "total",
    ]
    invoice = Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    assert to_csv([invoice]).splitlines()[1] == "INV-9,globex,NY,20.00,0.00,0.80,20.80"


def test_reports():
    batch = [
        Invoice(n, c, r, [LineItem("X", "x", 1, Decimal(p))])
        for n, c, r, p in [("1", "acme", "OR", "100.00"), ("2", "globex", "OR", "50.00"), ("3", "acme", "NY", "25.00")]
    ]
    assert revenue_by_region(batch) == {"NY": Decimal("26.00"), "OR": Decimal("150.00")}
    assert top_customers(batch, n=1) == [("acme", Decimal("126.00"))]
    assert average_invoice(batch) == Decimal("58.67")


def test_money_tax_and_discounts():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert tax_on(Decimal("2.00"), "CA") == Decimal("0.15")
    assert apply(Decimal("20.00"), [parse_code("SAVE40"), parse_code("OFF5")]) == Decimal("10.00")
