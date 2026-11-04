from datetime import date
from decimal import Decimal

from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem


def invoice(issued_on=date(2026, 11, 3)):
    return Invoice(
        "INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))], issued_on=issued_on
    )


def test_columns_are_stable():
    assert [header for header, _ in COLUMNS] == [
        "number", "issued", "customer", "region", "subtotal", "discount", "tax", "total",
    ]


def test_to_row():
    assert to_row(invoice()) == {
        "number": "INV-9",
        "issued": "03/11/2026",
        "customer": "globex",
        "region": "NY",
        "subtotal": "20.00",
        "discount": "0.00",
        "tax": "0.80",
        "total": "20.80",
    }


def test_missing_issue_date_is_left_blank():
    assert to_row(invoice(issued_on=None))["issued"] == ""


def test_to_csv():
    text = to_csv([invoice()])
    assert text.splitlines() == [
        "number,issued,customer,region,subtotal,discount,tax,total",
        "INV-9,03/11/2026,globex,NY,20.00,0.00,0.80,20.80",
    ]
