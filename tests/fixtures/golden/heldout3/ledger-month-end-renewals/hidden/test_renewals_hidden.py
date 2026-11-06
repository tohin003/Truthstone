"""Renewals stay on the anchor day (README, "Subscriptions"): a month without that day renews
on its last day, and the next renewal is back on the anchor day. add_months clamps."""

from calendar import monthrange
from datetime import date, timedelta

import pytest

from ledger.periods import add_months, renewal_dates


def anchored(start, months):
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1]))


def test_the_reported_subscription():
    assert renewal_dates(date(2026, 1, 31), 3) == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_the_readme_examples():
    assert renewal_dates(date(2026, 1, 31), 4) == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]
    assert renewal_dates(date(2028, 2, 29), 4, every=12) == [
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    ]
    assert renewal_dates(date(2026, 1, 10), 3) == [date(2026, 2, 10), date(2026, 3, 10), date(2026, 4, 10)]
    assert renewal_dates(date(2026, 3, 5), 2, every=12) == [date(2027, 3, 5), date(2028, 3, 5)]


@pytest.mark.parametrize("anchor", [29, 30, 31])
def test_month_end_anchors_over_two_years(anchor):
    start = date(2027, 1, anchor)
    assert renewal_dates(start, 24) == [anchored(start, k) for k in range(1, 25)]


def test_a_quarterly_plan_started_at_the_end_of_november():
    assert renewal_dates(date(2026, 11, 30), 4, every=3) == [
        date(2027, 2, 28),
        date(2027, 5, 30),
        date(2027, 8, 30),
        date(2027, 11, 30),
    ]


def test_add_months_clamps_to_the_last_day_of_a_short_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 1, 29), 13) == date(2027, 2, 28)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2026, 10, 31), 1) == date(2026, 11, 30)
    assert add_months(date(2026, 5, 20), -6) == date(2025, 11, 20)


def test_every_start_date_over_three_years_and_every_plan():
    first = date(2027, 1, 1)
    wrong = []
    for offset in range(3 * 366):
        start = first + timedelta(days=offset)
        for every in (1, 2, 3, 6, 12):
            count = 24 // every
            want = [anchored(start, every * k) for k in range(1, count + 1)]
            got = renewal_dates(start, count, every)
            if got != want:
                wrong.append(f"{start} every {every}: {got} != {want}")
    assert not wrong, f"{len(wrong)} wrong, e.g. {wrong[:3]}"


def test_unchanged_edges():
    assert renewal_dates(date(2026, 1, 31), 0) == []
    with pytest.raises(ValueError):
        renewal_dates(date(2026, 1, 10), 1, every=0)
