from datetime import datetime, timedelta, timezone

from datapipe.db import connect, daily_totals, init_schema, insert_orders

UTC = timezone.utc


def order(order_id, cents, created_at):
    return {
        "order_id": order_id,
        "email": "ana@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": "BE",
        "created_at": created_at,
    }


def test_daily_totals_group_by_the_utc_calendar_day(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_schema(conn)
    insert_orders(
        conn,
        [
            order("W-41", 1200, datetime(2026, 10, 3, 9, 15, tzinfo=UTC)),
            order("W-42", 900, datetime(2026, 10, 3, 22, 45, tzinfo=UTC)),
            order("W-43", 300, datetime(2026, 10, 3, 23, 59, tzinfo=UTC)),
            # 01:30 at UTC+2 on Oct 4 is 23:30 UTC on Oct 3.
            order("W-44", 50, datetime(2026, 10, 4, 1, 30, tzinfo=timezone(timedelta(hours=2)))),
            order("W-45", 700, datetime(2026, 10, 4, 0, 5, tzinfo=UTC)),
        ],
    )
    try:
        assert daily_totals(conn) == {"2026-10-03": 2450, "2026-10-04": 700}
        stored = [row[0] for row in conn.execute("SELECT created_at FROM orders ORDER BY order_id")]
        assert stored[1].startswith("2026-10-03T22:45:00")
    finally:
        conn.close()
