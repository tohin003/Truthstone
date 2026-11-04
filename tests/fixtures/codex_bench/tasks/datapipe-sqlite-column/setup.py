"""Create the developer's local data/app.db as datapipe 0.2.x left it.

Runs in the repository after the initial commit. The orders table still has the old `amt`
column. Its 50 rows stand for earlier imports whose export files are gone; they are
generated deterministically so that grading can check every one of them.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

CUSTOMERS = [
    "ana@example.com",
    "ben@example.com",
    "cara@example.com",
    "dev@example.com",
    "erin@example.com",
    "fay@example.com",
    "gus@example.com",
]
REGIONS = ["CA", "NY", "TX", "WA", "OR"]
START = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc)

OLD_SCHEMA = """
CREATE TABLE orders (
    order_id   TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    amt        INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    region     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX orders_by_email ON orders (email);
CREATE TABLE imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL
);
"""

ORDERS = [
    (
        f"A-{1001 + i}",
        CUSTOMERS[(i * 3) % len(CUSTOMERS)],
        500 + (i * 7919) % 45000,
        1 + (i * 2) % 4,
        REGIONS[i % len(REGIONS)],
        (START + timedelta(hours=45 * i)).isoformat(timespec="seconds"),
    )
    for i in range(50)
]
IMPORTS = [
    ("orders-2026-06.csv", 17, 16),
    ("orders-2026-07.csv", 18, 17),
    ("orders-2026-08.csv", 17, 16),
    ("orders-2026-09.csv", 1, 1),
]

path = Path("data") / "app.db"
path.parent.mkdir(exist_ok=True)
conn = sqlite3.connect(path)
conn.executescript(OLD_SCHEMA)
with conn:
    conn.executemany(
        "INSERT INTO orders (order_id, email, amt, quantity, region, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ORDERS,
    )
    conn.executemany("INSERT INTO imports (source, rows_read, rows_inserted) VALUES (?, ?, ?)", IMPORTS)
conn.close()
