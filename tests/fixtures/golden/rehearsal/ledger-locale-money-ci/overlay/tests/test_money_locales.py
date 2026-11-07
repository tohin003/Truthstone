"""Invoice amounts by locale: the examples the invoice templates were checked against (README)."""

from decimal import Decimal

import pytest

from ledger.money import MoneyError, format_money

NBSP = "\u00a0"  # no-break space, before a symbol written after the amount
NNBSP = "\u202f"  # narrow no-break space, the French thousands separator


def test_en_us_is_the_default():
    assert format_money(Decimal("1234.5"), "EUR") == "€1,234.50"
    assert format_money(Decimal("1234.5"), "EUR", locale="en-US") == "€1,234.50"
    assert format_money(Decimal("-5"), "USD", locale="en-US") == "-$5.00"


def test_en_gb():
    assert format_money(Decimal("-1234.5"), "GBP", locale="en-GB") == "-£1,234.50"


def test_de_de():
    assert format_money(Decimal("1234.5"), "EUR", locale="de-DE") == f"1.234,50{NBSP}€"
    assert format_money(Decimal("1234567.891"), "EUR", locale="de-DE") == f"1.234.567,89{NBSP}€"
    assert format_money(Decimal("-5"), "EUR", locale="de-DE") == f"-5,00{NBSP}€"
    assert format_money(Decimal("0.005"), "USD", locale="de-DE") == f"0,01{NBSP}$"


def test_fr_fr():
    assert format_money(Decimal("1234.5"), "EUR", locale="fr-FR") == f"1{NNBSP}234,50{NBSP}€"
    assert format_money(Decimal("999.999"), "EUR", locale="fr-FR") == f"1{NNBSP}000,00{NBSP}€"
    assert format_money(Decimal("-1234567"), "GBP", locale="fr-FR") == f"-1{NNBSP}234{NNBSP}567,00{NBSP}£"


def test_en_in_groups_in_twos_above_the_thousands():
    assert format_money(Decimal("1234567"), "USD", locale="en-IN") == "$12,34,567.00"
    assert format_money(Decimal("123456.78"), "EUR", locale="en-IN") == "€1,23,456.78"
    assert format_money(Decimal("1234.5"), "EUR", locale="en-IN") == "€1,234.50"
    assert format_money(Decimal("-999.99"), "GBP", locale="en-IN") == "-£999.99"


def test_unknown_locale():
    with pytest.raises(MoneyError):
        format_money(Decimal("1"), "EUR", locale="xx-XX")
