"""Subscription periods: when a subscription renews (README, "Subscriptions").

The billing service charges a subscription on each renewal date and uses
``renewal_dates`` to show customers their upcoming charges.
"""

from __future__ import annotations

from datetime import date


def add_months(day: date, months: int) -> date:
    """``day`` moved ``months`` calendar months forward (backward when negative)."""
    index = day.year * 12 + (day.month - 1) + months
    return day.replace(year=index // 12, month=index % 12 + 1)


def renewal_dates(start: date, count: int, every: int = 1) -> list[date]:
    """The first ``count`` renewal dates of a subscription that started on ``start``.

    The subscription renews every ``every`` months; ``start`` itself is not a renewal.
    """
    if every < 1:
        raise ValueError(f"every must be at least 1 month, got {every!r}")
    renewals: list[date] = []
    current = start
    for _ in range(count):
        current = add_months(current, every)
        renewals.append(current)
    return renewals
