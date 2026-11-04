"""Money helpers.

Amounts are ``Decimal`` values in the currency's major unit (dollars, euros). Rounding is
commercial: to whole cents, half away from zero.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


class MoneyError(ValueError):
    """A value could not be read as an amount of money."""


def to_decimal(value: object) -> Decimal:
    """Read ``value`` as a Decimal. Floats go through ``str`` to avoid binary noise."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError(f"not an amount: {value!r}") from exc


def quantize(amount: Decimal) -> Decimal:
    """Round to whole cents, half away from zero."""
    return to_decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def to_cents(amount: object) -> int:
    return int(quantize(to_decimal(amount)) * 100)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def format_money(amount: object, currency: str = "USD") -> str:
    """``$1,234.50``; negative amounts get a leading minus: ``-$5.00``."""
    value = quantize(to_decimal(amount))
    symbol = SYMBOLS.get(currency.upper())
    if symbol is None:
        raise MoneyError(f"unknown currency: {currency}")
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"
