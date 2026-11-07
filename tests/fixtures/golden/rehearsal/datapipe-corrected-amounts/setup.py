"""Build the developer's local reporting database, data/app.db (git-ignored, as *.db is).

It holds four imports: July, August and September from exports that are no longer in the
repository, and October's data/orders.csv, loaded with 0.3.0. That version stored an amount with
a thousands separator as the part before the first comma, so W-2002 ($1,240.00) holds 100 cents
and W-2007 (2,015.40) holds 200. Everything is generated deterministically (no randomness).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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

EMAILS = ["ana", "ben", "cara", "dev", "erin", "fay", "gus", "hana", "ivo", "jun"]
REGIONS = ["CA", "NY", "TX", "WA", "OR", "AZ"]
# (source, month, first order number, orders stored, rows read)
MONTHS = [
    ("orders-2026-07.csv", 7, 1501, 30, 31),
    ("orders-2026-08.csv", 8, 1601, 28, 28),
    ("orders-2026-09.csv", 9, 1701, 33, 34),
]
# October, as 0.3.0 stored data/orders.csv (W-2002 and W-2007 are the wrong ones).
OCTOBER = [
    ("W-2001", "ana@example.com", 1250, 1, "CA", "2026-10-01T08:12:00+00:00"),
    ("W-2002", "ben@example.com", 100, 2, "NY", "2026-10-01T09:30:00+00:00"),
    ("W-2003", "cara@example.com", 725, 1, "TX", "2026-10-01T17:45:00+00:00"),
    ("W-2004", "ana@example.com", 310, 1, "CA", "2026-10-02T11:05:00+00:00"),
    ("W-2005", "dev@example.com", -1250, 1, "WA", "2026-10-02T13:20:00+00:00"),
    ("W-2006", "erin@example.com", 8900, 3, "OR", "2026-10-02T19:02:00+00:00"),
    ("W-2007", "cara@example.com", 200, 1, "TX", "2026-10-03T07:48:00+00:00"),
    ("W-2008", "ben@example.com", 1999, 1, "NY", "2026-10-03T12:00:00+00:00"),
    ("W-2009", "fay@example.com", 500, 4, "CA", "2026-10-03T16:31:00+00:00"),
    ("W-2010", "dev@example.com", 4200, 1, "WA", "2026-10-04T10:15:00+00:00"),
]


def history():
    state = 20260701
    for _source, month, first, count, _read in MONTHS:
        for i in range(count):
            state = (state * 1103515245 + 12345) % 2**31
            cents = 300 + state % 89700  # $3.00 to $899.99: no thousands separators
            if state % 23 == 0:
                cents = -cents  # a refund
            day = 1 + (i * 28) // count
            hour, minute = state % 24, (state // 24) % 60
            yield (
                f"W-{first + i}",
                f"{EMAILS[state % len(EMAILS)]}@example.com",
                cents,
                1 + (state // 7) % 4,
                REGIONS[(state // 11) % len(REGIONS)],
                f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+00:00",
            )


def main() -> None:
    path = Path("data/app.db")
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    insert = (
        "INSERT INTO orders (order_id, email, amount_cents, quantity, region, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    with conn:
        conn.executemany(insert, list(history()))
        conn.executemany(insert, OCTOBER)
        log = [(source, read, stored) for source, _m, _f, stored, read in MONTHS]
        log.append(("orders.csv", 12, 10))
        conn.executemany("INSERT INTO imports (source, rows_read, rows_inserted) VALUES (?, ?, ?)", log)
    conn.close()


if __name__ == "__main__":
    main()
