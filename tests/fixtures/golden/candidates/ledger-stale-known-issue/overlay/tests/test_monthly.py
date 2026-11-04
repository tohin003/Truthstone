from datetime import date
from decimal import Decimal

from ledger.discounts import Discount
from ledger.invoice import Invoice, LineItem
from ledger.reports import monthly_revenue


def inv(number, region, price, issued_on, discounts=()):
    return Invoice(number, "acme", region, [LineItem("X", "x", 1, Decimal(price))], list(discounts), issued_on)


def test_monthly_revenue_groups_by_region():
    batch = [
        inv("1", "OR", "100.00", date(2026, 10, 5)),
        inv("2", "OR", "50.00", date(2026, 10, 12)),
        inv("3", "NY", "0.00", date(2026, 10, 20)),
    ]
    assert monthly_revenue(batch, 2026, 10) == {"NY": Decimal("0.00"), "OR": Decimal("150.00")}


def test_other_months_and_drafts_are_left_out():
    batch = [
        inv("1", "OR", "100.00", date(2026, 9, 30)),
        inv("2", "OR", "50.00", date(2026, 10, 1)),
        inv("3", "OR", "25.00", date(2026, 11, 1)),
        inv("4", "OR", "10.00", None),
    ]
    assert monthly_revenue(batch, 2026, 10) == {"OR": Decimal("50.00")}


def test_revenue_is_what_the_customers_pay():
    # After discounts and tax, like revenue_by_region: 200.00 - 10% = 180.00, plus 7.25% CA tax.
    batch = [inv("1", "CA", "200.00", date(2026, 10, 7), [Discount("percent", Decimal("10"), "SAVE10")])]
    assert monthly_revenue(batch, 2026, 10) == {"CA": Decimal("193.05")}


def test_a_month_includes_its_last_day():
    batch = [inv("1", "OR", "80.00", date(2026, 10, 31)), inv("2", "OR", "20.00", date(2026, 10, 30))]
    assert monthly_revenue(batch, 2026, 10) == {"OR": Decimal("100.00")}
