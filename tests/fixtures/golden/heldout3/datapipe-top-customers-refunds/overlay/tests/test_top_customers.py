from datetime import datetime, timezone

import pytest

from datapipe.db import connect, init_schema, insert_orders
from datapipe.report import render, report_runs, top_customers


def order(order_id, email, cents):
    return {
        "order_id": order_id,
        "email": email,
        "amount_cents": cents,
        "quantity": 1,
        "region": "CA",
        "created_at": datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "app.db")
    init_schema(connection)
    yield connection
    connection.close()


def test_top_customers_ranks_by_revenue(conn):
    insert_orders(
        conn,
        [order("W-1", "ana@example.com", 5000), order("W-2", "ben@example.com", 9000), order("W-3", "ana@example.com", 1000)],
    )
    assert top_customers(conn) == [("ben@example.com", 9000), ("ana@example.com", 6000)]


def test_top_customers_nets_refunds(conn):
    insert_orders(
        conn,
        [
            order("W-1", "ana@example.com", 6000),
            order("W-2", "ben@example.com", 9000),
            order("W-3", "ben@example.com", -8000),  # ben sent most of it back
            order("W-4", "cara@example.com", 2500),
        ],
    )
    assert top_customers(conn) == [
        ("ana@example.com", 6000),
        ("cara@example.com", 2500),
        ("ben@example.com", 1000),
    ]


def test_ties_are_listed_by_email(conn):
    insert_orders(conn, [order("W-1", "erin@example.com", 700), order("W-2", "dev@example.com", 700)])
    assert top_customers(conn) == [("dev@example.com", 700), ("erin@example.com", 700)]


def test_n_limits_the_list(conn):
    insert_orders(conn, [order(f"W-{i}", f"c{i}@example.com", 100 * i) for i in range(1, 8)])
    assert [email for email, _ in top_customers(conn, n=3)] == ["c7@example.com", "c6@example.com", "c5@example.com"]
    with pytest.raises(ValueError):
        top_customers(conn, n=0)


def test_each_run_is_recorded(conn):
    insert_orders(conn, [order("W-1", "ana@example.com", 100), order("W-2", "ben@example.com", 200)])
    top_customers(conn)
    top_customers(conn, n=1)
    assert report_runs(conn) == [2, 1]


def test_render():
    assert render([("ana@example.com", 124000), ("ben@example.com", -250)]) == (
        "1. ana@example.com  $1,240.00\n2. ben@example.com  -$2.50"
    )
