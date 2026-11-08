"""read_money: the inverse of format_money, as the request specifies it."""

from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money, read_money, quantize, to_cents


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$1,234.50", (Decimal("1234.50"), "USD")),
        ("-€5.00", (Decimal("-5.00"), "EUR")),
        ("£0.99", (Decimal("0.99"), "GBP")),
        ("12.30", (Decimal("12.30"), "USD")),
        ("€1,000", (Decimal("1000.00"), "EUR")),
        ("$1,234,567.89", (Decimal("1234567.89"), "USD")),
        ("-12", (Decimal("-12.00"), "USD")),
        ("$0.00", (Decimal("0.00"), "USD")),
    ],
)
def test_parses_the_formats_from_the_request(text, expected):
    amount, currency = read_money(text)
    assert (amount, currency) == expected
    assert isinstance(amount, Decimal)


def test_surrounding_whitespace_is_ignored():
    assert read_money("  $7.25 \n") == (Decimal("7.25"), "USD")
    assert read_money("\t-£3.10") == (Decimal("-3.10"), "GBP")


def test_amounts_are_rounded_to_cents_half_away_from_zero():
    assert read_money("12.345") == (Decimal("12.35"), "USD")
    assert read_money("-€0.125") == (Decimal("-0.13"), "EUR")
    assert read_money("£2.674") == (Decimal("2.67"), "GBP")
    assert to_cents(read_money("$19.999")[0]) == 2000


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
@pytest.mark.parametrize("amount", ["0", "0.5", "19.99", "1234.5", "-5", "-1234567.891", "1000000"])
def test_round_trips_with_format_money(amount, currency):
    assert read_money(format_money(Decimal(amount), currency)) == (quantize(Decimal(amount)), currency)


@pytest.mark.parametrize(
    "text", ["twelve", "", "   ", "$", "-", "¥100", "12.30 USD", "$12.30.5", "1 234", "5 EUR"]
)
def test_anything_else_raises_money_error(text):
    with pytest.raises(MoneyError):
        read_money(text)


def test_the_rest_of_the_module_is_unchanged():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert quantize(Decimal("2.675")) == Decimal("2.68")
    assert issubclass(MoneyError, ValueError)
