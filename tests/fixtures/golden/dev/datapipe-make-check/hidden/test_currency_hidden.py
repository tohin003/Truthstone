"""Orders carry a currency (USD when the export has none), and older databases keep loading."""

import sqlite3

from datapipe.db import (
    connect,
    daily_totals,
    import_log,
    init_schema,
    insert_orders,
    order_count,
    totals_by_currency,
    totals_by_email,
)
from datapipe.pipeline import run

# The schema datapipe 0.3.0 created, before orders had a currency.
SCHEMA_0_3 = """
CREATE TABLE orders (
    order_id     TEXT PRIMARY KEY,
    email        TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    quantity     INTEGER NOT NULL,
    region       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX orders_by_email ON orders (email);
CREATE TABLE imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL
);
INSERT INTO orders VALUES ('O-1', 'old@example.com', 1000, 1, 'CA', '2026-08-01T10:00:00+00:00');
INSERT INTO orders VALUES ('O-2', 'old@example.com', 2500, 1, 'NY', '2026-08-02T10:00:00+00:00');
INSERT INTO imports (source, rows_read, rows_inserted) VALUES ('orders-2026-08.csv', 2, 2);
"""

HEADER = "order_id,email,amount,quantity,region,created_at"


def export(tmp_path, text, name="export.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def old_database(tmp_path):
    path = tmp_path / "reporting.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_0_3)
    conn.close()
    return path


def totals(database):
    conn = connect(database)
    try:
        return totals_by_currency(conn)
    finally:
        conn.close()


def test_currency_is_stored_per_order(tmp_path):
    path = export(
        tmp_path,
        f"{HEADER},currency\n"
        "C-1,a@example.com,10.00,1,de,2026-10-01T08:00:00Z,EUR\n"
        "C-2,b@example.com,2.50,1,us,2026-10-01T09:00:00Z,USD\n"
        "C-3,c@example.com,4.00,1,de,2026-10-01T10:00:00Z,EUR\n"
        "C-4,d@example.com,7.00,1,gb,2026-10-01T11:00:00Z,GBP\n",
    )
    assert run(path, tmp_path / "app.db").inserted == 4
    assert totals(tmp_path / "app.db") == {"EUR": 1400, "GBP": 700, "USD": 250}


def test_a_blank_currency_means_usd(tmp_path):
    path = export(
        tmp_path,
        f"{HEADER},currency\n"
        "B-1,a@example.com,10.00,1,de,2026-10-01T08:00:00Z,EUR\n"
        "B-2,b@example.com,3.00,1,us,2026-10-01T09:00:00Z,\n",
    )
    run(path, tmp_path / "app.db")
    assert totals(tmp_path / "app.db") == {"EUR": 1000, "USD": 300}


def test_exports_without_a_currency_column_are_usd(tmp_path):
    path = export(
        tmp_path,
        f"{HEADER}\n"
        "U-1,a@example.com,12.50,1,ca,2026-10-01T08:00:00Z\n"
        'U-2,b@example.com,"$1,000.00",2,ny,2026-10-02T08:00:00Z\n',
    )
    run(path, tmp_path / "app.db")
    assert totals(tmp_path / "app.db") == {"USD": 101250}


def test_totals_by_currency_is_ordered_by_code(tmp_path):
    path = export(
        tmp_path,
        f"{HEADER},currency\n"
        "S-1,a@example.com,1.00,1,us,2026-10-01T08:00:00Z,USD\n"
        "S-2,a@example.com,1.00,1,ch,2026-10-01T08:00:00Z,CHF\n"
        "S-3,a@example.com,1.00,1,jp,2026-10-01T08:00:00Z,JPY\n"
        "S-4,a@example.com,1.00,1,de,2026-10-01T08:00:00Z,EUR\n",
    )
    run(path, tmp_path / "app.db")
    assert list(totals(tmp_path / "app.db")) == ["CHF", "EUR", "JPY", "USD"]


def test_rows_stored_without_a_currency_are_usd(tmp_path):
    from datetime import datetime, timezone

    conn = connect(tmp_path / "app.db")
    try:
        init_schema(conn)
        row = {
            "order_id": "R-1",
            "email": "a@example.com",
            "amount_cents": 990,
            "quantity": 1,
            "region": "CA",
            "created_at": datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc),
        }
        assert insert_orders(conn, [row]) == 1
        assert totals_by_currency(conn) == {"USD": 990}
    finally:
        conn.close()


def test_a_database_from_0_3_keeps_loading(tmp_path):
    database = old_database(tmp_path)
    path = export(
        tmp_path,
        f"{HEADER},currency\n"
        "O-2,old@example.com,25.00,1,ny,2026-08-02T10:00:00Z,USD\n"
        "N-1,new@example.com,30.00,1,de,2026-10-05T10:00:00Z,EUR\n"
        "N-2,new@example.com,5.00,1,us,2026-10-05T11:00:00Z,\n",
        name="orders-2026-10-05.csv",
    )
    summary = run(path, database)
    assert (summary.inserted, summary.already_present) == (2, 1)
    assert totals(database) == {"EUR": 3000, "USD": 1000 + 2500 + 500}
    conn = connect(database)
    try:
        assert order_count(conn) == 4
        assert import_log(conn)[0] == {"source": "orders-2026-08.csv", "rows_read": 2, "rows_inserted": 2}
        assert totals_by_email(conn) == {"new@example.com": 3500, "old@example.com": 3500}
    finally:
        conn.close()


def test_init_schema_is_repeatable_on_an_old_database(tmp_path):
    database = old_database(tmp_path)
    conn = connect(database)
    try:
        init_schema(conn)
        init_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        assert "currency" in columns
        assert order_count(conn) == 2
        assert totals_by_currency(conn) == {"USD": 3500}
    finally:
        conn.close()


def test_other_reports_are_unchanged(tmp_path):
    path = export(
        tmp_path,
        f"{HEADER},currency\n"
        "D-1,Ana@Example.com,10.00,1,de,2026-10-01T23:30:00Z,EUR\n"
        "D-2,ana@example.com,1.00,1,us,2026-10-02T00:30:00Z,USD\n",
    )
    run(path, tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"ana@example.com": 1100}
        assert daily_totals(conn) == {"2026-10-01": 1000, "2026-10-02": 100}
    finally:
        conn.close()
