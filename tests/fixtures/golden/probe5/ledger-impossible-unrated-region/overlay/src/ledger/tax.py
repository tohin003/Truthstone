"""Sales tax by region."""

from __future__ import annotations

from decimal import Decimal

from ledger.money import quantize

# Rates come from finance's signed rate sheet; what happens to a region without a rate is in
# rate_for's docstring.
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
    """The configured tax rate for ``region`` (any case).

    A region with no configured rate raises ``UnknownRegion``, here and so from ``tax_on``,
    ``Invoice.tax()`` and ``Invoice.total()``, instead of being billed at 0%: an invoice never
    goes out untaxed by accident. Rates come from finance's signed rate sheet only, and nobody
    adds a region at 0% as a placeholder (Oregon is in ``RATES`` at 0% because Oregon has no
    sales tax).
    """
    try:
        return RATES[region.upper()]
    except KeyError as exc:
        raise UnknownRegion(region) from exc


def tax_on(amount: Decimal, region: str) -> Decimal:
    """Tax due on ``amount`` in ``region``, rounded to whole cents."""
    return quantize(amount * rate_for(region))
