from datetime import datetime, timedelta, timezone

import pytest

from datapipe.db import (
    connect,
    daily_totals,
    import_log,
    init_schema,
    insert_orders,
    order_count,
    record_import,
    totals_by_email,
)

UTC = timezone.utc


def order(order_id, email="a@example.com", cents=100, created_at=None):
    return {
        "order_id": order_id,
        "email": email,
        "amount_cents": cents,
        "quantity": 1,
        "region": "CA",
        "created_at": created_at or datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "orders.db")
    init_schema(connection)
    yield connection
    connection.close()


def test_init_schema_is_idempotent(conn):
    init_schema(conn)
    assert order_count(conn) == 0


def test_insert_orders_returns_the_new_rows(conn):
    assert insert_orders(conn, [order("W-1"), order("W-2")]) == 2
    assert insert_orders(conn, []) == 0
    assert order_count(conn) == 2


def test_existing_orders_are_not_overwritten(conn):
    insert_orders(conn, [order("W-1", cents=100)])
    assert insert_orders(conn, [order("W-1", cents=999), order("W-2", cents=50)]) == 1
    assert totals_by_email(conn) == {"a@example.com": 150}


def test_totals_by_email(conn):
    insert_orders(
        conn,
        [order("W-1", "b@example.com", 250), order("W-2", "a@example.com", 100), order("W-3", "b@example.com", 50)],
    )
    assert totals_by_email(conn) == {"a@example.com": 100, "b@example.com": 300}


def test_daily_totals_use_utc_days(conn):
    minus_five = timezone(timedelta(hours=-5))
    insert_orders(
        conn,
        [
            order("W-1", cents=500, created_at=datetime(2026, 10, 1, 10, 0, tzinfo=UTC)),
            # 22:30 at UTC-5 on Oct 1 is 03:30 UTC on Oct 2.
            order("W-2", cents=1500, created_at=datetime(2026, 10, 1, 22, 30, tzinfo=minus_five)),
            order("W-3", cents=2000, created_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC)),
        ],
    )
    assert daily_totals(conn) == {"2026-10-01": 500, "2026-10-02": 3500}


def test_created_at_may_be_iso_text(conn):
    # The backfill of the old shop's orders passes timestamps as text.
    insert_orders(conn, [order("W-1", cents=700, created_at="2026-10-03T09:15:00+00:00")])
    assert daily_totals(conn) == {"2026-10-03": 700}


def test_import_log(conn):
    record_import(conn, "orders.csv", 12, 10)
    record_import(conn, "orders.csv", 12, 0)
    assert import_log(conn) == [
        {"source": "orders.csv", "rows_read": 12, "rows_inserted": 10},
        {"source": "orders.csv", "rows_read": 12, "rows_inserted": 0},
    ]
