"""The README's locale rules, on amounts the visible examples do not use."""

from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money

NBSP = " "
NNBSP = " "


@pytest.mark.parametrize(
    ("amount", "currency", "locale", "expected"),
    [
        ("0", "EUR", "de-DE", f"0,00{NBSP}€"),
        ("12", "GBP", "de-DE", f"12,00{NBSP}£"),
        ("1000", "EUR", "de-DE", f"1.000,00{NBSP}€"),
        ("-1234.567", "EUR", "de-DE", f"-1.234,57{NBSP}€"),
        ("100", "EUR", "fr-FR", f"100,00{NBSP}€"),
        ("12345.678", "USD", "fr-FR", f"12{NNBSP}345,68{NBSP}$"),
        ("-0.5", "EUR", "fr-FR", f"-0,50{NBSP}€"),
        ("100000", "GBP", "en-IN", "£1,00,000.00"),
        ("-12345678.9", "USD", "en-IN", "-$1,23,45,678.90"),
        ("999.995", "USD", "en-IN", "$1,000.00"),
        ("12.3", "EUR", "en-IN", "€12.30"),
        ("9876543.21", "GBP", "en-GB", "£9,876,543.21"),
        ("-0.125", "USD", "en-US", "-$0.13"),
        ("1000000", "EUR", "en-US", "€1,000,000.00"),
    ],
)
def test_locale_rules(amount, currency, locale, expected):
    assert format_money(Decimal(amount), currency, locale=locale) == expected


def test_the_default_is_unchanged():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money("0.004", "GBP") == "£0.00"


def test_unknown_locales_and_currencies_raise():
    for locale in ("en-AU", "pt-BR", "ja-JP"):
        with pytest.raises(MoneyError):
            format_money(Decimal("1"), "EUR", locale=locale)
    with pytest.raises(MoneyError):
        format_money(Decimal("1"), "XYZ", locale="de-DE")
