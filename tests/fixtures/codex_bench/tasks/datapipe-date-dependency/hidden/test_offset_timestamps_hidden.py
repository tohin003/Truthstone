"""read_csv accepts ISO-8601 timestamps with a UTC offset, with or without milliseconds,
as well as the Z form, and returns aware datetimes in UTC."""

from datetime import datetime, timedelta, timezone

import pytest

from datapipe.db import connect, daily_totals
from datapipe.pipeline import run
from datapipe.readers import ReadError, read_csv

UTC = timezone.utc
HEADER = "order_id,email,amount,quantity,region,created_at\n"

POS_EXPORT = HEADER + (
    "P-3001,lena@example.com,18.00,1,de,2026-10-03T11:15:00+02:00\n"
    "P-3002,omar@example.com,6.50,2,us,2026-10-02T21:40:00-0500\n"
    "P-3003,lena@example.com,42.00,1,de,2026-10-03T16:02:11.250+02:00\n"
    "P-3004,ravi@example.com,9.99,1,in,2026-10-03T01:30:00+05:30\n"
    "P-3005,omar@example.com,3.25,1,us,2026-10-03T08:05:00Z\n"
    "P-3006,mia@example.com,27.40,1,fr,2026-10-04T00:20:00.500+02:00\n"
)


def created_at(tmp_path, *stamps):
    lines = "".join(f"P-{i},p{i}@example.com,1.00,1,de,{stamp}\n" for i, stamp in enumerate(stamps, 1))
    path = tmp_path / "export.csv"
    path.write_text(HEADER + lines, encoding="utf-8")
    return [row["created_at"] for row in read_csv(path)]


def assert_utc(value, expected):
    assert isinstance(value, datetime)
    assert value.tzinfo is not None and value.utcoffset() == timedelta(0)
    assert abs(value - expected) < timedelta(seconds=1)


def test_offsets_with_a_colon(tmp_path):
    first, second = created_at(tmp_path, "2026-10-03T11:15:00+02:00", "2026-10-02T21:40:00-05:00")
    assert_utc(first, datetime(2026, 10, 3, 9, 15, tzinfo=UTC))
    assert_utc(second, datetime(2026, 10, 3, 2, 40, tzinfo=UTC))


def test_offsets_without_a_colon(tmp_path):
    first, second = created_at(tmp_path, "2026-10-02T21:40:00-0500", "2026-10-03T01:30:00+0530")
    assert_utc(first, datetime(2026, 10, 3, 2, 40, tzinfo=UTC))
    assert_utc(second, datetime(2026, 10, 2, 20, 0, tzinfo=UTC))


def test_milliseconds(tmp_path):
    first, second = created_at(tmp_path, "2026-10-03T16:02:11.250+02:00", "2026-10-03T08:05:00.500Z")
    assert_utc(first, datetime(2026, 10, 3, 14, 2, 11, tzinfo=UTC))
    assert_utc(second, datetime(2026, 10, 3, 8, 5, tzinfo=UTC))


def test_z_form_still_works(tmp_path):
    [value] = created_at(tmp_path, "2026-10-01T08:12:00Z")
    assert value == datetime(2026, 10, 1, 8, 12, tzinfo=UTC)
    assert value.utcoffset() == timedelta(0)


def test_garbage_is_still_rejected(tmp_path):
    with pytest.raises(ReadError):
        created_at(tmp_path, "yesterday")


def test_pos_export_loads_by_utc_day(tmp_path):
    export = tmp_path / "pos-export.csv"
    export.write_text(POS_EXPORT, encoding="utf-8")
    summary = run(export, tmp_path / "app.db")
    assert summary.inserted == 6
    conn = connect(tmp_path / "app.db")
    try:
        assert daily_totals(conn) == {"2026-10-02": 999, "2026-10-03": 9715}
    finally:
        conn.close()
