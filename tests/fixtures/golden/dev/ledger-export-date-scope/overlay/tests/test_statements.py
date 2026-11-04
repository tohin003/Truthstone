from datetime import date
from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.statements import statement


def invoice(number, customer, issued_on, price, quantity=1):
    return Invoice(
        number, customer, "NY", [LineItem("W-1", "Widget", quantity, Decimal(price))], issued_on=issued_on
    )


def test_statement_lists_the_customers_invoices_oldest_first():
    invoices = [
        invoice("INV-12", "globex", date(2026, 12, 1), "5.00"),
        invoice("INV-10", "acme", date(2026, 11, 20), "5.00"),
        invoice("INV-9", "globex", date(2026, 11, 3), "10.00", quantity=2),
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


def test_statement_with_no_invoices():
    assert statement("initech", [], as_of=date(2026, 7, 1)).splitlines() == [
        "Statement for initech",
        "As of 01/07/2026",
        "",
        "",
        "Balance: $0.00",
    ]
