from datetime import date
from decimal import Decimal

import pytest

from ledger.installments import due_dates, split


def test_split_rules():
    assert split(Decimal("100.00"), 3) == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert split(Decimal("1.00"), 7) == [Decimal("0.15")] * 2 + [Decimal("0.14")] * 5
    assert split(Decimal("10.00"), 4) == [Decimal("2.50")] * 4
    assert split(Decimal("54.97"), 1) == [Decimal("54.97")]
    for total in ("0.02", "7.77", "58.96", "1234.56", "99999.99"):
        for count in range(1, 13):
            parts = split(Decimal(total), count)
            assert sum(parts) == Decimal(total)
            assert parts == sorted(parts, reverse=True)
            assert max(parts) - min(parts) <= Decimal("0.01")
            assert all(part == part.quantize(Decimal("0.01")) for part in parts)


def test_split_refuses_bad_counts():
    for bad in (0, 13, 24, -3):
        with pytest.raises(ValueError):
            split(Decimal("10.00"), bad)


def test_due_dates_follow_the_calendar_month():
    assert due_dates(date(2026, 8, 31), 7) == [
        date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31), date(2026, 11, 30),
        date(2026, 12, 31), date(2027, 1, 31), date(2027, 2, 28),
    ]
    assert due_dates(date(2027, 12, 29), 3) == [date(2027, 12, 29), date(2028, 1, 29), date(2028, 2, 29)]
    assert due_dates(date(2026, 3, 1), 12)[-1] == date(2027, 2, 1)
    assert due_dates(date(2026, 5, 20), 1) == [date(2026, 5, 20)]
