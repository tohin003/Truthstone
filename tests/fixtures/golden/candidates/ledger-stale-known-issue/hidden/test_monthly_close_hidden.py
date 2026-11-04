"""October's month-end figures: invoice totals, every day of the month, nothing from other months."""

from datetime import date
from decimal import Decimal

from ledger.discounts import Discount
from ledger.invoice import Invoice, LineItem
from ledger.reports import monthly_revenue


def inv(number, region, price, issued_on, discounts=()):
    return Invoice(number, "acme", region, [LineItem("X", "x", 1, Decimal(price))], list(discounts), issued_on)


def test_october_close_counts_every_invoice_total():
    batch = [
        inv("1", "CA", "200.00", date(2026, 10, 1), [Discount("percent", Decimal("10"), "SAVE10")]),
        inv("2", "CA", "50.00", date(2026, 10, 31)),
        inv("3", "NY", "100.00", date(2026, 10, 15)),
        inv("4", "OR", "80.00", date(2026, 10, 31)),
        inv("5", "OR", "70.00", date(2026, 11, 1)),
        inv("6", "OR", "60.00", date(2026, 9, 30)),
        inv("7", "CA", "999.00", None),
    ]
    assert monthly_revenue(batch, 2026, 10) == {
        "CA": Decimal("246.68"),
        "NY": Decimal("104.00"),
        "OR": Decimal("80.00"),
    }


def test_the_last_day_of_any_month_counts():
    for year, month, last in [(2026, 2, 28), (2028, 2, 29), (2026, 4, 30), (2026, 12, 31)]:
        batch = [inv("1", "OR", "10.00", date(year, month, last)), inv("2", "OR", "5.00", date(year, month, 1))]
        assert monthly_revenue(batch, year, month) == {"OR": Decimal("15.00")}, (year, month)


def test_the_next_month_and_the_same_month_last_year_do_not_count():
    batch = [
        inv("1", "OR", "10.00", date(2027, 1, 1)),
        inv("2", "OR", "20.00", date(2025, 12, 31)),
        inv("3", "OR", "40.00", date(2026, 12, 31)),
    ]
    assert monthly_revenue(batch, 2026, 12) == {"OR": Decimal("40.00")}


def test_an_empty_month():
    assert monthly_revenue([inv("1", "OR", "10.00", date(2026, 10, 3))], 2026, 11) == {}
