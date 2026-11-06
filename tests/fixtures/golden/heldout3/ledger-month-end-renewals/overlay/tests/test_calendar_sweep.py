"""The calendar sweep: ledger.periods against every start date from 1 January 1900 to
31 December 2199 (three centuries, so 1900 and 2100, which are not leap years, are in it),
every plan length we sell and two years of renewals each (README, "Development"). It takes
about ten seconds, so the default run leaves it out (`addopts` in pyproject.toml); run it
with `pytest -m calendar`.

The rule is the README's ("Subscriptions"): a subscription renews on its anchor day, the
day of the month it started; in a month without that day it renews on the month's last
day, and the renewal after that is back on the anchor day.
"""

from calendar import monthrange
from datetime import date, timedelta

import pytest

from ledger.periods import add_months, renewal_dates

pytestmark = pytest.mark.calendar

FIRST, LAST = date(1900, 1, 1), date(2199, 12, 31)
PLANS = (1, 2, 3, 6, 12)  # months between renewals
YEARS_OF_RENEWALS = 2


def every_day(first=FIRST, last=LAST):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def month_after(day, months, anchor):
    """``anchor`` (a day of the month) in the month ``months`` after ``day``'s, clamped."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(anchor, monthrange(year, month + 1)[1]))


def report(problems, checked):
    shown = "\n".join(problems[:12])
    return f"{len(problems)} of {checked} dates wrong; the first ones:\n{shown}"


def test_add_months_lands_on_the_same_day_or_the_last_day_of_the_month():
    problems, checked = [], 0
    for day in every_day():
        for months in (-13, -1, 1, 2, 3, 6, 12, 25):
            checked += 1
            want = month_after(day, months, day.day)
            try:
                got = add_months(day, months)
            except Exception as exc:  # noqa: BLE001 - the sweep reports every failure
                problems.append(f"add_months({day}, {months}) raised {type(exc).__name__}: {exc}")
                continue
            if got != want:
                problems.append(f"add_months({day}, {months}) is {got}, expected {want}")
    assert not problems, report(problems, checked)


def test_renewals_stay_on_the_anchor_day():
    problems, checked = [], 0
    for start in every_day():
        for every in PLANS:
            count = YEARS_OF_RENEWALS * 12 // every
            checked += count
            want = [month_after(start, every * k, start.day) for k in range(1, count + 1)]
            try:
                got = renewal_dates(start, count, every)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"renewal_dates({start}, {count}, every={every}) raised {type(exc).__name__}: {exc}")
                continue
            for k, (g, w) in enumerate(zip(got, want), start=1):
                if g != w:
                    problems.append(f"start {start}, every {every} month(s): renewal {k} is {g}, expected {w}")
                    break
            if len(got) != count:
                problems.append(f"renewal_dates({start}, {count}, every={every}) gave {len(got)} dates")
    assert not problems, report(problems, checked)
