from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.reports import revenue_by_region
from ledger.statement import statement


def make(region="CA", codes=()):
    return Invoice(
        "INV-7",
        "acme",
        region,
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code(code) for code in codes],
    )


def test_sales_tax_is_the_new_name():
    invoice = make()
    assert invoice.sales_tax() == Decimal("3.99")
    assert invoice.total() == Decimal("58.96")
    assert make(codes=["SAVE10"]).sales_tax() == Decimal("3.59")


def test_the_old_name_is_gone():
    assert not hasattr(make(), "tax")
    assert not hasattr(Invoice, "tax")


def test_csv_export_keeps_its_tax_column():
    assert [header for header, _ in COLUMNS] == [
        "number", "customer", "region", "subtotal", "discount", "tax", "total",
    ]
    assert to_row(make())["tax"] == "3.99"
    assert to_csv([make()]).splitlines()[1] == "INV-7,acme,CA,54.97,0.00,3.99,58.96"


def test_portal_statement_still_renders():
    assert statement(make()) == (
        "Invoice INV-7 for acme\n"
        "Subtotal        $54.97\n"
        "Discount         $0.00\n"
        "Sales tax        $3.99\n"
        "Total           $58.96\n"
    )


def test_reports_unaffected():
    assert revenue_by_region([make(), make(region="OR")]) == {"CA": Decimal("58.96"), "OR": Decimal("54.97")}
