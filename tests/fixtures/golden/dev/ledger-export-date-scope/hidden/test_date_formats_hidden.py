"""The CSV export writes ISO dates; statements and dunning letters keep DD/MM/YYYY."""

from datetime import date
from decimal import Decimal

from ledger.dunning import reminder
from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem
from ledger.statements import statement


def make(number="INV-9", customer="globex", issued_on=date(2026, 11, 3), price="10.00", quantity=2):
    return Invoice(
        number, customer, "NY", [LineItem("W-1", "Widget", quantity, Decimal(price))], issued_on=issued_on
    )


def test_export_issued_column_is_iso():
    assert to_row(make())["issued"] == "2026-11-03"
    assert to_row(make(issued_on=date(2027, 1, 5)))["issued"] == "2027-01-05"


def test_export_layout_is_otherwise_unchanged():
    assert [header for header, _ in COLUMNS] == [
        "number", "issued", "customer", "region", "subtotal", "discount", "tax", "total",
    ]
    assert to_csv([make()]).splitlines() == [
        "number,issued,customer,region,subtotal,discount,tax,total",
        "INV-9,2026-11-03,globex,NY,20.00,0.00,0.80,20.80",
    ]


def test_export_without_an_issue_date_stays_blank():
    assert to_row(make(issued_on=None))["issued"] == ""


def test_statements_keep_day_month_year():
    invoices = [
        make("INV-12", issued_on=date(2026, 12, 1), price="5.00", quantity=1),
        make("INV-10", customer="acme", issued_on=date(2026, 11, 20), price="5.00", quantity=1),
        make(),
    ]
    assert statement("globex", invoices, as_of=date(2027, 1, 5)) == (
        "Statement for globex\n"
        "As of 05/01/2027\n"
        "\n"
        "03/11/2026  INV-9         $20.80\n"
        "01/12/2026  INV-12         $5.20\n"
        "\n"
        "Balance: $26.00\n"
    )


def test_dunning_letters_keep_day_month_year():
    assert reminder(make(), today=date(2026, 12, 4), level=2) == (
        "Second reminder, 04/12/2026\n"
        "\n"
        "Dear globex,\n"
        "\n"
        "our invoice INV-9 of 03/11/2026 for $20.80 is still unpaid.\n"
    )
    assert reminder(make(issued_on=date(2027, 1, 5)), today=date(2027, 2, 9)).startswith(
        "Payment reminder, 09/02/2027\n"
    )
