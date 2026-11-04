from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money, from_cents, quantize, to_cents, to_decimal


def test_to_decimal_reads_strings_and_floats():
    assert to_decimal("12.30") == Decimal("12.30")
    assert to_decimal(0.1) == Decimal("0.1")


def test_to_decimal_rejects_garbage():
    with pytest.raises(MoneyError):
        to_decimal("twelve")


def test_quantize_rounds_half_away_from_zero():
    assert quantize(Decimal("0.125")) == Decimal("0.13")
    assert quantize(Decimal("-0.125")) == Decimal("-0.13")
    assert quantize(Decimal("2.675")) == Decimal("2.68")


def test_cents_round_trip():
    assert to_cents("19.99") == 1999
    assert from_cents(1999) == Decimal("19.99")


def test_format_money():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money("0.004", "GBP") == "£0.00"


def test_format_money_unknown_currency():
    with pytest.raises(MoneyError):
        format_money(1, "XYZ")


def test_format_money_yen_has_no_minor_unit():
    assert format_money(Decimal("1234.5"), "JPY") == "¥1,235"
    assert format_money(Decimal("-1234.5"), "JPY") == "-¥1,235"
    assert format_money(Decimal("2.495"), "JPY") == "¥2"


def test_format_money_never_shows_negative_zero():
    assert format_money(Decimal("-0.4"), "JPY") == "¥0"
    assert format_money(Decimal("-0.004"), "EUR") == "€0.00"
