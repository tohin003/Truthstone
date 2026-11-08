"""Prototype: forecast daily demand from past sales with a trailing moving average.

Abandoned in favour of the till's own demand reports (see the CHANGELOG); nothing in stockroom
imports this module.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def moving_average(daily_sales: Sequence[int], window: int = 7) -> float:
    """Average units sold per day over the last ``window`` days (fewer if there is less history)."""
    if window < 1:
        raise ValueError(f"window must be at least 1, got {window!r}")
    recent = list(daily_sales)[-window:]
    return sum(recent) / len(recent) if recent else 0.0


def forecast(daily_sales: Sequence[int], days: int, window: int = 7) -> int:
    """Units expected to sell over the next ``days`` days, rounded up."""
    return math.ceil(round(moving_average(daily_sales, window) * days, 9))
