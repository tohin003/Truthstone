"""Hidden checks: the ShopNext export loads end to end (byte-order mark and UTC offsets), times are
stored in UTC, and the old export format and the reader's errors are unchanged."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from datapipe.db import connect, daily_totals, order_count
from datapipe.pipeline import run
from datapipe.readers import ReadError, parse_timestamp, read_csv

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "data" / "shopnext-2026-10-05.csv"
UTC = timezone.utc


def test_the_shopnext_sample_imports(tmp_path):
    summary = run(SAMPLE, tmp_path / "app.db")
    assert (summary.rows_read, summary.inserted) == (7, 7)
    conn = connect(tmp_path / "app.db")
    stamps = dict(conn.execute("SELECT order_id, created_at FROM orders").fetchall())
    assert order_count(conn) == 7
    assert stamps["SN-100231"] == "2026-10-04T07:12:00+00:00"
    assert stamps["SN-100234"] == "2026-10-05T06:55:00+00:00"
    assert stamps["SN-100235"] == "2026-10-04T23:30:00+00:00"
    assert stamps["SN-100236"] == "2026-10-05T08:00:00+00:00"
    assert daily_totals(conn) == {"2026-10-04": 2490 + 109900 - 490 + 5800, "2026-10-05": 31000 + 1200 + 7550}
    conn.close()


def test_a_byte_order_mark_is_not_part_of_the_first_column(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("﻿order_id,email,amount,created_at\nW-1,a@example.com,1.00,2026-10-01T08:12:00Z\n".encode())
    [row] = read_csv(path)
    assert row["order_id"] == "W-1"


def test_offsets_and_z_read_as_the_same_instant():
    assert parse_timestamp("2026-10-01T08:12:00Z") == datetime(2026, 10, 1, 8, 12, tzinfo=UTC)
    assert parse_timestamp("2026-10-01T10:12:00+02:00") == datetime(2026, 10, 1, 8, 12, tzinfo=UTC)
    assert parse_timestamp("2026-09-30T23:42:00-08:30") == datetime(2026, 10, 1, 8, 12, tzinfo=UTC)
    assert parse_timestamp("2026-10-01T08:12:00Z").utcoffset().total_seconds() == 0


def test_bad_timestamps_are_still_reported(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("order_id,email,amount,created_at\nW-1,a@example.com,1.00,yesterday\n", encoding="utf-8")
    with pytest.raises(ReadError, match="line 2"):
        read_csv(path)


def test_the_old_export_still_loads(tmp_path):
    summary = run(REPO / "data" / "orders.csv", tmp_path / "app.db")
    assert summary.inserted > 0
