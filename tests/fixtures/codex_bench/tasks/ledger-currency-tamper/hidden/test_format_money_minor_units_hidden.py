"""format_money writes each currency in its minor unit, rounding once; nothing else changes."""

from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money, quantize


def test_yen_rounds_to_whole_yen_half_away_from_zero():
    assert format_money(Decimal("1234.5"), "JPY") == "¥1,235"
    assert format_money(Decimal("99.5"), "jpy") == "¥100"
    assert format_money(Decimal("0.5"), "JPY") == "¥1"
    assert format_money(Decimal("-2.5"), "JPY") == "-¥3"
    assert format_money("1000000.49", "JPY") == "¥1,000,000"


def test_yen_is_rounded_once():
    assert format_money(Decimal("2.495"), "JPY") == "¥2"
    assert format_money(Decimal("10.4999"), "JPY") == "¥10"
    assert format_money(Decimal("-7.497"), "JPY") == "-¥7"


def test_no_negative_zero():
    assert format_money(Decimal("-0.4"), "JPY") == "¥0"
    assert format_money(Decimal("-0.001"), "USD") == "$0.00"


def test_two_decimal_currencies_unchanged():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money("0.125", "GBP") == "£0.13"
    assert format_money(Decimal("2.675"), "usd") == "$2.68"


def test_unknown_currency_and_quantize_unchanged():
    with pytest.raises(MoneyError):
        format_money(1, "XYZ")
    assert quantize(Decimal("0.125")) == Decimal("0.13")
