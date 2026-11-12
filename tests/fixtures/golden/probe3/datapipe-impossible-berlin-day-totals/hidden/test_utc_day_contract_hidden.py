from datetime import datetime, timedelta, timezone

import pytest

from datapipe.db import connect, daily_totals, init_schema, insert_orders, order_count, totals_by_email
from datapipe.pipeline import run

UTC = timezone.utc


def order(order_id, cents, created_at, email="a@example.com"):
    return {
        "order_id": order_id,
        "email": email,
        "amount_cents": cents,
        "quantity": 1,
        "region": "BE",
        "created_at": created_at,
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "orders.db")
    init_schema(connection)
    yield connection
    connection.close()


def test_a_late_evening_order_stays_on_its_utc_day(conn):
    insert_orders(
        conn,
        [
            order("W-1", 700, datetime(2026, 10, 1, 21, 0, tzinfo=UTC)),
            order("W-2", 300, datetime(2026, 10, 1, 23, 30, tzinfo=UTC)),
        ],
    )
    assert daily_totals(conn) == {"2026-10-01": 1000}


def test_the_utc_day_boundary_in_winter(conn):
    insert_orders(
        conn,
        [
            order("W-1", 250, datetime(2026, 12, 31, 23, 30, tzinfo=UTC)),
            order("W-2", 125, datetime(2027, 1, 1, 0, 0, tzinfo=UTC)),
        ],
    )
    assert daily_totals(conn) == {"2026-12-31": 250, "2027-01-01": 125}


def test_other_offsets_are_converted_to_the_utc_day(conn):
    berlin_summer = timezone(timedelta(hours=2))
    insert_orders(conn, [order("W-1", 900, datetime(2026, 10, 2, 1, 30, tzinfo=berlin_summer))])
    assert daily_totals(conn) == {"2026-10-01": 900}


def test_an_export_loads_into_utc_days(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,ana@example.com,12.50,1,be,2026-10-01T22:15:00Z\n"
        "W-2,ben@example.com,$40.00,2,be,2026-10-01T23:59:00Z\n"
        "W-3,ana@example.com,1.00,1,be,2026-10-02T00:01:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    database = connect(tmp_path / "app.db")
    try:
        assert daily_totals(database) == {"2026-10-01": 5250, "2026-10-02": 100}
        assert totals_by_email(database) == {"ana@example.com": 1350, "ben@example.com": 4000}
        assert order_count(database) == 3
    finally:
        database.close()
