from decimal import Decimal

from ledger.money import format_money


def test_negative_amounts_lead_with_the_sign():
    assert format_money(Decimal("-5")) == "-$5.00"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money(Decimal("-1234.5"), "GBP") == "-£1,234.50"


def test_positive_amounts_unchanged():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money("0.004", "GBP") == "£0.00"
    assert format_money(Decimal("0")) == "$0.00"


def test_rounding_still_commercial():
    assert format_money(Decimal("-0.125")) == "-$0.13"
