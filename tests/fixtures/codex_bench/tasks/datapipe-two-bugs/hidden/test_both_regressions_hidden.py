"""Both regressions are fixed: thousands separators parse, and daily totals use UTC days."""

from datetime import datetime, timedelta, timezone

import pytest

from datapipe.db import connect, daily_totals, init_schema, insert_orders, totals_by_email
from datapipe.pipeline import run
from datapipe.transforms import TransformError, parse_amount

UTC = timezone.utc


def test_amounts_with_thousands_separators():
    assert parse_amount("1,240.00") == 124000
    assert parse_amount("$12,000") == 1200000
    assert parse_amount("-1,000.05") == -100005


def test_other_amounts_unchanged():
    assert parse_amount("12.50") == 1250
    assert parse_amount(" $3.99 ") == 399
    for bad in ("abc", "12.345", ""):
        with pytest.raises(TransformError):
            parse_amount(bad)


def order(order_id, cents, created_at):
    return {
        "order_id": order_id,
        "email": "a@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": "CA",
        "created_at": created_at,
    }


def test_daily_totals_bucket_by_utc_day(tmp_path):
    plus_nine = timezone(timedelta(hours=9))
    minus_seven = timezone(timedelta(hours=-7))
    conn = connect(tmp_path / "orders.db")
    try:
        init_schema(conn)
        insert_orders(
            conn,
            [
                order("H-1", 300, datetime(2026, 10, 5, 7, 0, tzinfo=plus_nine)),  # Oct 4, 22:00 UTC
                order("H-2", 700, datetime(2026, 10, 4, 19, 30, tzinfo=minus_seven)),  # Oct 5, 02:30 UTC
                order("H-3", 1000, datetime(2026, 10, 5, 12, 0, tzinfo=UTC)),
            ],
        )
        assert daily_totals(conn) == {"2026-10-04": 300, "2026-10-05": 1700}
    finally:
        conn.close()


def test_export_with_large_amounts_loads(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        'W-1,ana@example.com,"$1,240.00",1,ca,2026-10-01T08:12:00Z\n'
        'W-2,ben@example.com,"2,015.40",1,ny,2026-10-01T09:30:00Z\n'
        "W-3,ana@example.com,12.50,1,ca,2026-10-02T11:05:00Z\n",
        encoding="utf-8",
    )
    assert run(export, tmp_path / "app.db").inserted == 3
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"ana@example.com": 125250, "ben@example.com": 201540}
    finally:
        conn.close()
