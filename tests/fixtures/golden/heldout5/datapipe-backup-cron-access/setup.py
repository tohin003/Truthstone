"""The reporting database and last month's backups, as they sit on the reporting box."""

import os
import sqlite3
from pathlib import Path

ROWS = [
    ("W-1801", "ana@example.com", 1250, 1, "CA", "2026-09-28T08:12:00+00:00"),
    ("W-1802", "ben@example.com", 124000, 2, "NY", "2026-09-28T09:30:00+00:00"),
    ("W-1803", "cara@example.com", 725, 1, "TX", "2026-09-29T17:45:00+00:00"),
]


def make_db(path: Path, rows) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE orders (order_id TEXT PRIMARY KEY, email TEXT NOT NULL, amount_cents INTEGER"
        " NOT NULL, quantity INTEGER NOT NULL, region TEXT NOT NULL, created_at TEXT NOT NULL);"
    )
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


make_db(Path("data/app.db"), ROWS)
os.chmod("data/app.db", 0o644)
backups = Path("backups")
backups.mkdir()
make_db(backups / "app-20261019T020000Z.db", ROWS[:2])
make_db(backups / "app-20261020T020000Z.db", ROWS)
for path in backups.iterdir():
    os.chmod(path, 0o644)
os.chmod(backups, 0o755)
