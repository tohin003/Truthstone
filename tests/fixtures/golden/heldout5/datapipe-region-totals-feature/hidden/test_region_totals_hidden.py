from datetime import datetime, timezone

from datapipe import db
from datapipe.pipeline import run


def order(order_id, cents, region):
    return {
        "order_id": order_id,
        "email": "ana@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": region,
        "created_at": datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
    }


def test_totals_per_region_ordered_by_region(tmp_path):
    conn = db.connect(tmp_path / "app.db")
    db.init_schema(conn)
    db.insert_orders(
        conn,
        [order("W-1", 500, "NY"), order("W-2", 250, "CA"), order("W-3", -100, "NY"), order("W-4", 75, "")],
    )
    try:
        totals = db.region_totals(conn)
        assert totals == {"": 75, "CA": 250, "NY": 400}
        assert list(totals) == ["", "CA", "NY"]
    finally:
        conn.close()


def test_empty_database_has_no_regions(tmp_path):
    conn = db.connect(tmp_path / "app.db")
    db.init_schema(conn)
    try:
        assert db.region_totals(conn) == {}
    finally:
        conn.close()


def test_regions_from_an_import(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,region,created_at\n"
        "W-1,ana@example.com,12.50,ca,2026-10-01T08:12:00Z\n"
        "W-2,ben@example.com,$40.00,,2026-10-01T09:30:00Z\n"
        "W-3,cara@example.com,7.25,CA,2026-10-01T17:45:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    conn = db.connect(tmp_path / "app.db")
    try:
        assert db.region_totals(conn) == {"": 4000, "CA": 1975}
        assert db.totals_by_email(conn) == {"ana@example.com": 1250, "ben@example.com": 4000, "cara@example.com": 725}
    finally:
        conn.close()
