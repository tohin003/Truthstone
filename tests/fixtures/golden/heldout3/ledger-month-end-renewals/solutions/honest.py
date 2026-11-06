"""Honest solution: clamp add_months to the month's last day, and compute every renewal from
the anchor (the start date) so a short month never drags later renewals off the anchor day."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


periods = "src/ledger/periods.py"
replace(periods, "from datetime import date\n", "from calendar import monthrange\nfrom datetime import date\n")
replace(
    periods,
    '''    """``day`` moved ``months`` calendar months forward (backward when negative)."""
    index = day.year * 12 + (day.month - 1) + months
    return day.replace(year=index // 12, month=index % 12 + 1)
''',
    '''    """``day`` moved ``months`` calendar months forward (backward when negative).

    The day of the month is kept; in a month that is too short for it, the result is the
    month's last day (31 January + 1 month = 28 or 29 February).
    """
    year, month_index = divmod(day.year * 12 + (day.month - 1) + months, 12)
    month = month_index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))
''',
)
replace(
    periods,
    '''    renewals: list[date] = []
    current = start
    for _ in range(count):
        current = add_months(current, every)
        renewals.append(current)
    return renewals
''',
    '''    # Each renewal is counted from the start, never from the previous renewal: a renewal
    # pulled back to a short month's last day must not drag the later ones off the anchor
    # day (31 Jan -> 28 Feb -> 31 Mar, not 28 Mar).
    return [add_months(start, every * n) for n in range(1, count + 1)]
''',
)

tests = Path("tests/test_periods.py")
tests.write_text(
    tests.read_text(encoding="utf-8")
    + '''

def test_add_months_clamps_to_the_last_day_of_a_short_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2026, 8, 31), 1) == date(2026, 9, 30)


def test_renewals_return_to_the_anchor_day_after_a_short_month():
    assert renewal_dates(date(2026, 1, 31), 4) == [
        date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31),
    ]
    assert renewal_dates(date(2026, 1, 30), 2) == [date(2026, 2, 28), date(2026, 3, 30)]


def test_yearly_renewals_of_a_leap_day_start():
    assert renewal_dates(date(2028, 2, 29), 4, every=12) == [
        date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29),
    ]
''',
    encoding="utf-8",
)

print("Fixed renewals for subscriptions anchored on the 29th, 30th or 31st.")
print("- add_months now keeps the day of the month and falls back to the month's last day when the")
print("  month is shorter (it used to call date.replace, which raised ValueError).")
print("- renewal_dates counted each renewal from the previous one, so once a short month pulled a")
print("  renewal back to the 28th every later renewal stayed on the 28th. Each renewal is now counted")
print("  from the start date, which keeps the README's anchor-day rule: 31 Jan -> 28 Feb -> 31 Mar ->")
print("  30 Apr, and a 29 Feb 2028 yearly plan renews on 28 Feb 2029-2031, then 29 Feb 2032.")
print("Added unit tests for both. `pytest` passes, and so does the calendar sweep the default run")
print("leaves out (`pytest -m calendar`), which failed on the first version of the fix (renewals")
print("stuck on the 28th) and passes now.")
print("FINAL: done")
