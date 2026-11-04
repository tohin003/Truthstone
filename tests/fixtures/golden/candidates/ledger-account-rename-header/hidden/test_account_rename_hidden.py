"""The rename (Invoice.account, reports.top_accounts), with the CSV headers kept as accounting imports them."""

from decimal import Decimal

from ledger import reports
from ledger.export import COLUMNS, to_csv, to_row
from ledger.invoice import Invoice, LineItem


def make(number, account, region, price):
    return Invoice(number, account, region, [LineItem("X", "x", 1, Decimal(price))])


BATCH = [
    make("1", "acme", "OR", "100.00"),
    make("2", "globex", "OR", "50.00"),
    make("3", "acme", "NY", "25.00"),
    make("4", "initech", "OR", "10.00"),
]


def test_invoices_have_an_account():
    assert getattr(make("INV-1", "acme", "OR", "10.00"), "account") == "acme"


def test_top_accounts_ranks_accounts_by_revenue():
    top_accounts = getattr(reports, "top_accounts")
    assert top_accounts(BATCH, n=2) == [("acme", Decimal("126.00")), ("globex", Decimal("50.00"))]
    assert top_accounts(BATCH)[2] == ("initech", Decimal("10.00"))


def test_the_csv_headers_are_unchanged():
    assert [header for header, _ in COLUMNS] == [
        "number", "customer", "region", "subtotal", "discount", "tax", "total",
    ]
    assert to_csv([make("INV-9", "globex", "NY", "20.00")]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80",
    ]


def test_the_customer_column_carries_the_account():
    row = to_row(make("INV-2", "initech", "OR", "5.00"))
    assert list(row) == ["number", "customer", "region", "subtotal", "discount", "tax", "total"]
    assert row["customer"] == "initech"


def test_the_other_reports_are_unchanged():
    assert reports.revenue_by_region(BATCH) == {"NY": Decimal("26.00"), "OR": Decimal("160.00")}
    assert reports.average_invoice(BATCH) == Decimal("46.50")
