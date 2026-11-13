from datetime import date
from decimal import Decimal

import pytest

from ledger.installments import due_dates, split


def test_even_split():
    assert split(Decimal("10.00"), 4) == [Decimal("2.50")] * 4


def test_single_installment_is_the_total():
    assert split(Decimal("54.97"), 1) == [Decimal("54.97")]


def test_count_must_be_one_to_twelve():
    for bad in (0, 13, -1):
        with pytest.raises(ValueError):
            split(Decimal("10.00"), bad)


def test_extra_cents_go_to_the_earliest_installments():
    assert split(Decimal("100.00"), 3) == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert split(Decimal("0.05"), 3) == [Decimal("0.02"), Decimal("0.02"), Decimal("0.01")]
    # 5896 cents in 12: 491 each and 4 cents over, so the first four are 4.92.
    assert split(Decimal("58.96"), 12)[:5] == [Decimal("4.92")] * 4 + [Decimal("4.91")]


def test_installments_add_up_to_the_total():
    for total in ("0.01", "19.99", "58.96", "1000.00", "333.33"):
        for count in range(1, 13):
            parts = split(Decimal(total), count)
            assert sum(parts) == Decimal(total), (total, count)
            assert max(parts) - min(parts) <= Decimal("0.01"), (total, count)


def test_monthly_due_dates():
    assert due_dates(date(2026, 11, 15), 3) == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


def test_month_end_due_dates_clamp_without_drifting():
    assert due_dates(date(2026, 1, 31), 4) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30),
    ]
    assert due_dates(date(2028, 1, 30), 2) == [date(2028, 1, 30), date(2028, 2, 29)]
