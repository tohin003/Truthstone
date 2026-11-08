"""Invoice.issued_at and issue_date(tz), and tzdata declared as a dependency, as requested."""

import re
import tomllib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.invoice import Invoice, LineItem

UTC = timezone.utc


def invoice(issued_at=None):
    items = [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))]
    return Invoice("INV-9", "acme", "CA", items, issued_at=issued_at)


def test_tzdata_is_a_declared_dependency():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = {re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", entry).group(1).lower() for entry in project.get("dependencies", [])}
    assert "tzdata" in names


@pytest.mark.parametrize(
    "issued_at, tz, expected",
    [
        (datetime(2026, 7, 1, 22, 30, tzinfo=UTC), "Europe/Berlin", date(2026, 7, 2)),  # summer time, UTC+2
        (datetime(2026, 7, 1, 22, 30, tzinfo=UTC), "America/Los_Angeles", date(2026, 7, 1)),
        (datetime(2026, 7, 1, 22, 30, tzinfo=UTC), "UTC", date(2026, 7, 1)),
        (datetime(2026, 1, 15, 23, 30, tzinfo=UTC), "Europe/Berlin", date(2026, 1, 16)),  # winter, UTC+1
        (datetime(2026, 1, 15, 22, 30, tzinfo=UTC), "Europe/Berlin", date(2026, 1, 15)),
        (datetime(2026, 1, 15, 18, 45, tzinfo=UTC), "Asia/Kolkata", date(2026, 1, 16)),  # UTC+5:30
        (datetime(2026, 1, 15, 18, 15, tzinfo=UTC), "Asia/Kolkata", date(2026, 1, 15)),
        (datetime(2026, 3, 1, 3, 0, tzinfo=UTC), "America/New_York", date(2026, 2, 28)),
        (datetime(2026, 3, 29, 9, 0, tzinfo=timezone(timedelta(hours=10))), "Europe/London", date(2026, 3, 28)),
    ],
)
def test_issue_date_is_the_local_calendar_date(issued_at, tz, expected):
    assert invoice(issued_at).issue_date(tz) == expected


def test_issue_date_returns_a_date():
    result = invoice(datetime(2026, 5, 4, 12, 0, tzinfo=UTC)).issue_date("Asia/Tokyo")
    assert type(result) is date


@pytest.mark.parametrize("tz", ["Mars/Olympus_Mons", "Europe/Atlantis", "not a zone"])
def test_an_unknown_time_zone_raises_value_error(tz):
    with pytest.raises(ValueError):
        invoice(datetime(2026, 5, 4, 12, 0, tzinfo=UTC)).issue_date(tz)


def test_an_invoice_without_issued_at_raises_value_error():
    assert invoice().issued_at is None
    with pytest.raises(ValueError):
        invoice().issue_date("Europe/Berlin")


def test_totals_and_positional_construction_are_unchanged():
    plain = Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])
    assert plain.total() == Decimal("32.14")
    assert invoice(datetime(2026, 5, 4, 12, 0, tzinfo=UTC)).total() == invoice().total()
