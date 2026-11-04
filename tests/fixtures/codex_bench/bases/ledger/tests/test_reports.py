from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.reports import average_invoice, revenue_by_region, top_customers


def inv(number, customer, region, price):
    return Invoice(number, customer, region, [LineItem("X", "x", 1, Decimal(price))])


BATCH = [
    inv("1", "acme", "OR", "100.00"),
    inv("2", "globex", "OR", "50.00"),
    inv("3", "acme", "NY", "25.00"),
    inv("4", "initech", "OR", "10.00"),
]


def test_revenue_by_region():
    assert revenue_by_region(BATCH) == {"NY": Decimal("26.00"), "OR": Decimal("160.00")}


def test_top_customers():
    assert top_customers(BATCH, n=2) == [("acme", Decimal("126.00")), ("globex", Decimal("50.00"))]


def test_average_invoice():
    assert average_invoice(BATCH) == Decimal("46.50")


def test_average_of_nothing():
    assert average_invoice([]) == Decimal("0.00")
