"""Exports with UTC offsets load correctly: read as the right instant, stored and totalled in UTC."""

from datetime import datetime, timedelta, timezone

import pytest

from datapipe.__main__ import main
from datapipe.db import connect, daily_totals, init_schema, insert_orders
from datapipe.pipeline import run
from datapipe.readers import parse_timestamp, read_csv

UTC = timezone.utc
HEADER = "order_id,email,amount,quantity,region,created_at\n"


def test_offset_timestamps_are_read_as_the_instant_they_name():
    assert parse_timestamp("2026-11-02T21:30:00-05:00") == datetime(2026, 11, 3, 2, 30, tzinfo=UTC)
    assert parse_timestamp("2026-11-02T09:15:00+01:00") == datetime(2026, 11, 2, 8, 15, tzinfo=UTC)
    assert parse_timestamp("2026-11-02T21:30:00-05:00").utcoffset() is not None


def test_z_timestamps_still_work():
    parsed = parse_timestamp("2026-10-03T09:15:00Z")
    assert parsed == datetime(2026, 10, 3, 9, 15, tzinfo=UTC)
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-02T10:00:00Z", ""])
def test_garbage_is_still_rejected(bad):
    with pytest.raises(ValueError):
        parse_timestamp(bad)


def _load(tmp_path, body):
    export = tmp_path / "export.csv"
    export.write_text(HEADER + body, encoding="utf-8")
    database = tmp_path / "app.db"
    run(export, database)
    return connect(database)


def test_orders_from_an_offset_export_are_totalled_by_utc_day(tmp_path):
    conn = _load(
        tmp_path,
        "N-1,a@example.com,10.00,1,ny,2026-11-02T21:30:00-05:00\n"  # 02:30 UTC on Nov 3
        "N-2,b@example.com,20.00,1,ny,2026-11-02T18:00:00-05:00\n"  # 23:00 UTC on Nov 2
        "N-3,c@example.com,5.00,1,ny,2026-11-03T08:00:00Z\n",
    )
    assert daily_totals(conn) == {"2026-11-02": 2000, "2026-11-03": 1500}
    conn.close()


def test_stored_timestamps_are_utc(tmp_path):
    conn = _load(tmp_path, "N-1,a@example.com,10.00,1,ny,2026-11-02T21:30:00-05:00\n")
    [stored] = [row[0] for row in conn.execute("SELECT created_at FROM orders")]
    conn.close()
    assert stored.startswith("2026-11-03")
    assert datetime.fromisoformat(stored) == datetime(2026, 11, 3, 2, 30, tzinfo=UTC)
    assert datetime.fromisoformat(stored).utcoffset() == timedelta(0)


def test_insert_orders_stores_aware_datetimes_in_utc(tmp_path):
    conn = connect(tmp_path / "orders.db")
    init_schema(conn)
    order = {"order_id": "N-1", "email": "a@example.com", "amount_cents": 700, "quantity": 1, "region": "NY"}
    eastern = timezone(timedelta(hours=-5))
    insert_orders(conn, [{**order, "created_at": datetime(2026, 11, 2, 21, 30, tzinfo=eastern)}])
    insert_orders(conn, [{**order, "order_id": "N-2", "created_at": datetime(2026, 11, 2, 12, 0)}])  # naive: UTC
    assert daily_totals(conn) == {"2026-11-02": 700, "2026-11-03": 700}
    conn.close()


def test_the_shops_new_export_loads_from_the_command_line(tmp_path, capsys):
    assert main(["data/orders-2026-11.csv", str(tmp_path / "app.db")]) == 0
    assert "6 inserted" in capsys.readouterr().out
    conn = connect(tmp_path / "app.db")
    assert daily_totals(conn) == {
        "2026-11-01": 1800,
        "2026-11-02": 6450 + 725,
        "2026-11-03": -1800 + 112000,
        "2026-11-04": 4200,
    }
    conn.close()


def test_old_exports_still_load(tmp_path):
    rows = read_csv(_write(tmp_path, "W-1,a@example.com,1.00,1,ca,2026-10-01T08:12:00Z\n"))
    assert rows[0]["created_at"] == datetime(2026, 10, 1, 8, 12, tzinfo=UTC)


def _write(tmp_path, body):
    path = tmp_path / "old.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path
