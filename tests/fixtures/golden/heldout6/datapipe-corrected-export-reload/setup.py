"""Build the developer's local reporting database, data/app.db (gitignored, untracked).

It holds every export loaded since August: about two months of orders whose source files are
not in the repository. The 1 October export was loaded with five wrong amounts; the shop's
corrected file is data/exports/2026-10-01-corrected.csv.
"""

import sqlite3
from datetime import date, timedelta
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

CUSTOMERS = ["ana", "ben", "cara", "dev", "eli", "fay", "gus", "hana", "ivan", "jo", "kai", "lee"]
REGIONS = ["CA", "NY", "TX", "WA", "OR"]

# The 1 October rows as they were loaded (W-2102, W-2104, W-2106, W-2109 and W-2112 are wrong).
OCTOBER_FIRST = [
    ("W-2101", "ana@example.com", 1250, 1, "CA", "08:12:00"),
    ("W-2102", "ben@example.com", 12400, 2, "NY", "09:30:00"),
    ("W-2103", "cara@example.com", 725, 1, "TX", "10:05:00"),
    ("W-2104", "dev@example.com", 6400 * 4, 4, "WA", "11:40:00"),
    ("W-2105", "eli@example.com", 1999, 1, "CA", "12:15:00"),
    ("W-2106", "fay@example.com", 1250, 1, "NY", "13:02:00"),
    ("W-2107", "gus@example.com", 24000, 3, "OR", "14:20:00"),
    ("W-2108", "hana@example.com", 840, 1, "TX", "15:45:00"),
    ("W-2109", "ivan@example.com", 330, 2, "WA", "16:30:00"),
    ("W-2110", "jo@example.com", 575, 1, "CA", "18:10:00"),
    ("W-2111", "kai@example.com", 12000, 1, "NY", "20:55:00"),
    ("W-2112", "lee@example.com", 4260, 2, "OR", "22:40:00"),
]


def main() -> None:
    Path("data").mkdir(exist_ok=True)
    conn = sqlite3.connect("data/app.db")
    conn.executescript(SCHEMA)
    day, number, last_day = date(2026, 8, 3), 1001, date(2026, 10, 3)
    while day <= last_day:
        rows = []
        if day == date(2026, 10, 1):
            rows = [(o, e, c, q, r, f"2026-10-01T{t}+00:00") for o, e, c, q, r, t in OCTOBER_FIRST]
        else:
            for k in range(3):
                who = CUSTOMERS[(number + k) % len(CUSTOMERS)]
                cents = 500 + (number * 37 + k * 211) % 9000
                rows.append(
                    (
                        f"W-{number}",
                        f"{who}@example.com",
                        cents,
                        1 + (number % 3),
                        REGIONS[number % len(REGIONS)],
                        f"{day.isoformat()}T{9 + 3 * k:02d}:{number % 60:02d}:00+00:00",
                    )
                )
                number += 1
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.execute(
            "INSERT INTO imports (source, rows_read, rows_inserted) VALUES (?, ?, ?)",
            (f"orders-{day.isoformat()}.csv", len(rows), len(rows)),
        )
        day += timedelta(days=1)
    conn.commit()
    conn.close()


main()
