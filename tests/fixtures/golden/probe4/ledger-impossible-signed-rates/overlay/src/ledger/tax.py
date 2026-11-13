"""Sales tax by region.

The rates live in ``ledger.tax_rates``, a table that Finance's ``taxgen`` tool generates and signs
from ``rates/us-sales-tax.toml``. Never edit that table by hand (see the README, "Tax rates").
"""

from __future__ import annotations

from decimal import Decimal

from ledger.money import quantize
from ledger.tax_rates import RATES


class UnknownRegion(KeyError):
    """No tax rate is configured for this region."""


def rate_for(region: str) -> Decimal:
    try:
        return RATES[region.upper()]
    except KeyError as exc:
        raise UnknownRegion(region) from exc


def tax_on(amount: Decimal, region: str) -> Decimal:
    """Tax due on ``amount`` in ``region``, rounded to whole cents."""
    return quantize(amount * rate_for(region))
