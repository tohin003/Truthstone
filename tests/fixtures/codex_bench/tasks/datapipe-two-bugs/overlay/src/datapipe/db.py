"""SQLite storage for cleaned orders.

``orders`` is keyed by ``order_id``. Timestamps are stored as ISO-8601 text in UTC, so
the first ten characters of ``created_at`` are the order's UTC calendar day.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id     TEXT PRIMARY KEY,
    email        TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    quantity     INTEGER NOT NULL,
    region       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_by_email ON orders (email);
CREATE TABLE IF NOT EXISTS imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL
);
"""

_INSERT_ORDER = (
    "INSERT OR IGNORE INTO orders (order_id, email, amount_cents, quantity, region, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the database at ``path``, creating the file if needed."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create whichever tables and indexes do not exist yet."""
    conn.executescript(SCHEMA)


def _record(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["order_id"],
        row["email"],
        row["amount_cents"],
        row["quantity"],
        row["region"],
        row["created_at"].isoformat(timespec="seconds"),
    )


def insert_orders(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    """Store cleaned rows and return how many were new.

    A row whose ``order_id`` is already stored is skipped; the stored row is not updated.
    """
    records = [_record(row) for row in rows]
    if not records:
        return 0
    with conn:
        cursor = conn.executemany(_INSERT_ORDER, records)
    return cursor.rowcount


def record_import(conn: sqlite3.Connection, source: str, rows_read: int, rows_inserted: int) -> None:
    """Append one entry to the import log."""
    with conn:
        conn.execute(
            "INSERT INTO imports (source, rows_read, rows_inserted) VALUES (?, ?, ?)",
            (source, rows_read, rows_inserted),
        )


def order_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


def totals_by_email(conn: sqlite3.Connection) -> dict[str, int]:
    """Total ``amount_cents`` per customer, ordered by email."""
    rows = conn.execute(
        "SELECT email, SUM(amount_cents) AS total FROM orders GROUP BY email ORDER BY email"
    )
    return {row["email"]: row["total"] for row in rows}


def daily_totals(conn: sqlite3.Connection) -> dict[str, int]:
    """Total ``amount_cents`` per UTC calendar day, keyed ``YYYY-MM-DD``."""
    rows = conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, SUM(amount_cents) AS total "
        "FROM orders GROUP BY day ORDER BY day"
    )
    return {row["day"]: row["total"] for row in rows}


def import_log(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every recorded import, oldest first."""
    rows = conn.execute("SELECT source, rows_read, rows_inserted FROM imports ORDER BY id")
    return [dict(row) for row in rows]
