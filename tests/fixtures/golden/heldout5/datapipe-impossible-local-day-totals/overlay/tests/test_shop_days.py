"""The shop's day: the Berlin office reads the daily report against its own calendar."""

from datetime import datetime, timezone

import pytest

from datapipe.db import connect, daily_totals, init_schema, insert_orders

UTC = timezone.utc


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "app.db")
    init_schema(connection)
    yield connection
    connection.close()


def order(order_id, cents, created_at):
    return {
        "order_id": order_id,
        "email": "ana@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": "BE",
        "created_at": created_at,
    }


def test_late_evening_orders_count_on_the_shops_day(conn):
    insert_orders(
        conn,
        [
            order("W-31", 1200, datetime(2026, 10, 3, 9, 15, tzinfo=UTC)),
            # 22:45 UTC on Oct 3 is 00:45 on Oct 4 in Berlin, where the shop is.
            order("W-32", 900, datetime(2026, 10, 3, 22, 45, tzinfo=UTC)),
        ],
    )
    assert daily_totals(conn) == {"2026-10-03": 1200, "2026-10-04": 900}
