"""db.py's documented contract: timestamps are stored as ISO-8601 text in UTC, so the first ten
characters of created_at are the order's UTC day; created_at may be a datetime or ISO text."""

from datetime import datetime, timedelta, timezone

import pytest

from datapipe.db import connect, daily_totals, init_schema, insert_orders


def order(order_id, created_at, cents=100):
    return {
        "order_id": order_id,
        "email": "a@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": "CA",
        "created_at": created_at,
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "orders.db")
    init_schema(connection)
    yield connection
    connection.close()


def stored(conn, order_id):
    return conn.execute("SELECT created_at FROM orders WHERE order_id = ?", (order_id,)).fetchone()[0]


def assert_utc_text(text, expected):
    assert text[:19] == expected
    assert datetime.fromisoformat(text).utcoffset() == timedelta(0)


def test_datetimes_with_an_offset_are_stored_in_utc(conn):
    minus_five = timezone(timedelta(hours=-5))
    insert_orders(conn, [order("W-1", datetime(2026, 10, 1, 22, 30, tzinfo=minus_five))])
    assert_utc_text(stored(conn, "W-1"), "2026-10-02T03:30:00")


def test_iso_text_with_an_offset_is_stored_in_utc(conn):
    insert_orders(conn, [order("W-1", "2026-10-01T23:45:00+02:00"), order("W-2", "2026-10-01T20:00:00-06:00")])
    assert_utc_text(stored(conn, "W-1"), "2026-10-01T21:45:00")
    assert_utc_text(stored(conn, "W-2"), "2026-10-02T02:00:00")


def test_daily_totals_group_by_utc_day(conn):
    plus_nine = timezone(timedelta(hours=9))
    insert_orders(
        conn,
        [
            order("W-1", datetime(2026, 10, 2, 7, 0, tzinfo=plus_nine), cents=300),  # Oct 1, 22:00 UTC
            order("W-2", "2026-10-01T21:00:00-05:00", cents=200),  # Oct 2, 02:00 UTC
            order("W-3", datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc), cents=100),
        ],
    )
    assert daily_totals(conn) == {"2026-10-01": 300, "2026-10-02": 300}


def test_utc_input_is_unchanged(conn):
    insert_orders(conn, [order("W-1", datetime(2026, 10, 3, 9, 15, tzinfo=timezone.utc))])
    assert_utc_text(stored(conn, "W-1"), "2026-10-03T09:15:00")
