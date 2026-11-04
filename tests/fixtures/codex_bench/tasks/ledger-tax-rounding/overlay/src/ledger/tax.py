"""Sales tax by region."""

from __future__ import annotations

from decimal import Decimal

RATES: dict[str, Decimal] = {
    "CA": Decimal("0.0725"),
    "NY": Decimal("0.04"),
    "TX": Decimal("0.0625"),
    "WA": Decimal("0.065"),
    "OR": Decimal("0"),
}


class UnknownRegion(KeyError):
    """No tax rate is configured for this region."""


def rate_for(region: str) -> Decimal:
    try:
        return RATES[region.upper()]
    except KeyError as exc:
        raise UnknownRegion(region) from exc


def tax_on(amount: Decimal, region: str) -> Decimal:
    """Tax due on ``amount`` in ``region``, rounded to whole cents."""
    return round(amount * rate_for(region), 2)
