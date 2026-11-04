"""CHF is written as the code, a space and the amount; the other currencies are unchanged."""

from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money


def test_chf_is_written_with_its_code():
    assert format_money(Decimal("1234.5"), "CHF") == "CHF 1,234.50"
    assert format_money(Decimal("0.125"), "CHF") == "CHF 0.13"
    assert format_money("7", "CHF") == "CHF 7.00"
    assert format_money(Decimal("1234567.891"), "CHF") == "CHF 1,234,567.89"


def test_negative_chf_leads_with_the_sign():
    assert format_money(Decimal("-5"), "CHF") == "-CHF 5.00"
    assert format_money(Decimal("-1234.5"), "CHF") == "-CHF 1,234.50"


def test_existing_currencies_unchanged():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money("0.004", "GBP") == "£0.00"
    assert format_money(Decimal("-1234.5"), "usd") == "-$1,234.50"


def test_unknown_currency_still_rejected():
    with pytest.raises(MoneyError):
        format_money(1, "XYZ")
