"""Tallyport FX rates: the /v2/rates payload, parsed into Decimal rates per currency."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def parse_rates(payload: Any) -> dict[str, Decimal]:
    """``{"base": "EUR", "as_of": ..., "rates": [{"currency": "USD", "rate": "1.0842"}, ...]}``
    -> ``{"USD": Decimal("1.0842"), ...}``. Raises ValueError for anything else."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rates"), list):
        raise ValueError("expected an object with a 'rates' list")
    if not isinstance(payload.get("base"), str):
        raise ValueError("expected a 'base' currency")
    rates: dict[str, Decimal] = {}
    for entry in payload["rates"]:
        try:
            currency, rate = entry["currency"], Decimal(entry["rate"])
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise ValueError(f"bad rate entry {entry!r}") from exc
        if not (isinstance(currency, str) and len(currency) == 3 and rate > 0):
            raise ValueError(f"bad rate entry {entry!r}")
        rates[currency] = rate
    return rates
