from datetime import date

import pytest

from ledger.periods import add_months, renewal_dates


def test_add_months_keeps_the_day_of_the_month():
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)
    assert add_months(date(2026, 11, 3), 3) == date(2027, 2, 3)
    assert add_months(date(2026, 5, 20), -6) == date(2025, 11, 20)
    assert add_months(date(2026, 5, 20), 0) == date(2026, 5, 20)


def test_monthly_renewals():
    assert renewal_dates(date(2026, 1, 10), 3) == [date(2026, 2, 10), date(2026, 3, 10), date(2026, 4, 10)]


def test_quarterly_and_yearly_renewals():
    assert renewal_dates(date(2026, 3, 5), 2, every=3) == [date(2026, 6, 5), date(2026, 9, 5)]
    assert renewal_dates(date(2026, 3, 5), 2, every=12) == [date(2027, 3, 5), date(2028, 3, 5)]


def test_renewals_cross_the_new_year():
    assert renewal_dates(date(2026, 11, 28), 3) == [date(2026, 12, 28), date(2027, 1, 28), date(2027, 2, 28)]


def test_no_renewals_requested():
    assert renewal_dates(date(2026, 1, 10), 0) == []


def test_every_must_be_at_least_one_month():
    with pytest.raises(ValueError):
        renewal_dates(date(2026, 1, 10), 3, every=0)
