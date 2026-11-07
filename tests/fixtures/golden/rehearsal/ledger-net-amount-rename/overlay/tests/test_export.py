from decimal import Decimal

from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem


def invoice():
    return Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])


def test_columns_are_stable():
    assert [header for header, _ in COLUMNS] == [
        "number", "customer", "region", "subtotal", "discount", "tax", "total",
    ]


def test_to_row():
    assert to_row(invoice()) == {
        "number": "INV-9",
        "customer": "globex",
        "region": "NY",
        "subtotal": "20.00",
        "discount": "0.00",
        "tax": "0.80",
        "total": "20.80",
    }


def test_to_csv():
    text = to_csv([invoice()])
    assert text.splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80",
    ]


def test_summary_profile():
    assert to_csv([invoice()], profile="summary").splitlines() == ["invoice,region,total", "INV-9,NY,20.80"]
