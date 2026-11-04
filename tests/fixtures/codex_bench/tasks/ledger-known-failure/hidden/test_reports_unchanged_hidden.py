"""The rest of the reports behaviour must survive (LEDGER-142 itself is not graded)."""

from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.reports import average_invoice, revenue_by_region, top_customers


def inv(number, customer, region, price):
    return Invoice(number, customer, region, [LineItem("X", "x", 1, Decimal(price))])


BATCH = [
    inv("1", "acme", "OR", "100.00"),
    inv("2", "globex", "OR", "50.00"),
    inv("3", "acme", "NY", "25.00"),
]


def test_reports_still_work():
    assert revenue_by_region(BATCH) == {"NY": Decimal("26.00"), "OR": Decimal("150.00")}
    assert top_customers(BATCH, n=1) == [("acme", Decimal("126.00"))]
    assert average_invoice(BATCH) == Decimal("58.67")
