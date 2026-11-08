from datetime import datetime, timezone

from datapipe.db import connect, init_schema, insert_orders
from datapipe.regions import region_names, totals_by_region


def order(order_id, region, cents):
    return {
        "order_id": order_id,
        "email": "a@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": region,
        "created_at": datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc),
    }


def test_region_names_come_from_the_lookup_table():
    names = region_names()
    assert names["CA"] == "California"
    assert names["NY"] == "New York"
    assert names["TX"] == "Texas"


def test_totals_by_region_are_keyed_by_name(tmp_path):
    conn = connect(tmp_path / "orders.db")
    init_schema(conn)
    insert_orders(conn, [order("W-1", "CA", 1000), order("W-2", "TX", 250), order("W-3", "CA", 500), order("W-4", "ZZ", 100)])
    assert totals_by_region(conn) == {"California": 1500, "Texas": 250, "ZZ": 100}
    conn.close()
