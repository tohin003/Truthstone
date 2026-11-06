"""The weekly report as documented: net revenue (refunds count against the customer), ties by email,
every run recorded where the email job can see it, and the database never left locked."""

import sqlite3
from datetime import datetime, timezone

import pytest

from datapipe.db import connect, init_schema, insert_orders, order_count
from datapipe.pipeline import run
from datapipe.report import render, report_runs, top_customers

HEADER = "order_id,email,amount,quantity,region,created_at\n"


def order(order_id, email, cents):
    return {
        "order_id": order_id,
        "email": email,
        "amount_cents": cents,
        "quantity": 1,
        "region": "NY",
        "created_at": datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc),
    }


ORDERS = [
    order("W-1", "ana@example.com", 4000),
    order("W-2", "ben@example.com", 12000),
    order("W-3", "ben@example.com", -11000),
    order("W-4", "cara@example.com", 3000),
    order("W-5", "cara@example.com", 1000),
    order("W-6", "dev@example.com", 4000),
    order("W-7", "erin@example.com", 500),
    order("W-8", "erin@example.com", -900),
]


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "app.db"
    conn = connect(path)
    init_schema(conn)
    insert_orders(conn, ORDERS)
    conn.close()
    return path


def test_refunds_count_against_the_customer(database):
    conn = connect(database)
    assert top_customers(conn, n=5) == [
        ("ana@example.com", 4000),
        ("cara@example.com", 4000),
        ("dev@example.com", 4000),
        ("ben@example.com", 1000),
        ("erin@example.com", -400),
    ]
    conn.close()


def test_n_takes_the_top_of_the_net_ranking(database):
    conn = connect(database)
    assert top_customers(conn, n=2) == [("ana@example.com", 4000), ("cara@example.com", 4000)]
    conn.close()


def test_a_refund_only_customer_is_below_everyone_else(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_schema(conn)
    insert_orders(conn, [order("W-1", "zed@example.com", -500), order("W-2", "amy@example.com", 100)])
    assert top_customers(conn) == [("amy@example.com", 100), ("zed@example.com", -500)]
    conn.close()


def test_every_run_is_visible_to_the_email_job(database):
    service = connect(database)
    top_customers(service, n=2)
    top_customers(service, n=3)
    email_job = sqlite3.connect(str(database), timeout=0.5)
    assert [row[0] for row in email_job.execute("SELECT listed FROM report_runs ORDER BY id")] == [2, 3]
    email_job.close()
    service.close()


def test_the_run_is_kept_when_the_service_disconnects(database):
    service = connect(database)
    top_customers(service, n=4)
    service.close()
    conn = connect(database)
    assert report_runs(conn) == [4]
    conn.close()


def test_a_report_never_leaves_the_database_locked(database):
    service = connect(database)
    top_customers(service)
    writer = sqlite3.connect(str(database), timeout=0.5)
    with writer:
        writer.execute(
            "INSERT INTO orders (order_id, email, amount_cents, quantity, region, created_at) "
            "VALUES ('W-99', 'fay@example.com', 100, 1, 'CA', '2026-10-13T08:00:00+00:00')"
        )
    writer.close()
    assert top_customers(service)[-1] == ("fay@example.com", 100)
    service.close()


def test_the_nightly_import_loads_while_the_service_is_connected(database, tmp_path):
    service = connect(database)
    top_customers(service)
    export = tmp_path / "later.csv"
    export.write_text(HEADER + "W-50,gus@example.com,9.00,1,wa,2026-10-13T10:00:00Z\n", encoding="utf-8")
    summary = run(export, database)
    assert summary.inserted == 1
    assert order_count(service) == len(ORDERS) + 1
    service.close()


def test_render_is_unchanged():
    assert render([("ana@example.com", 4000), ("erin@example.com", -400)]) == (
        "1. ana@example.com  $40.00\n2. erin@example.com  -$4.00"
    )
