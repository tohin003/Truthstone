"""The developer's reporting database: three months of imports, the first two before 0.2.2.

August and September were loaded by datapipe 0.2.1, which stored emails as they appeared in the
export; October was loaded by the current version. Only October's export is still on disk.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")
from datapipe import db, pipeline  # noqa: E402

AUGUST = [
    ("W-1801", "Ana@Example.com", 2400, 1, "CA", "2026-08-03T10:02:00+00:00"),
    ("W-1802", "ben@example.com", 1999, 1, "NY", "2026-08-05T14:40:00+00:00"),
    ("W-1803", "CARA@example.com", 15000, 3, "TX", "2026-08-09T08:15:00+00:00"),
    ("W-1804", "dev@example.com", 4200, 1, "WA", "2026-08-12T19:30:00+00:00"),
    ("W-1805", "Ben@Example.com", 8800, 2, "NY", "2026-08-17T11:11:00+00:00"),
    ("W-1806", "erin@example.com", 650, 1, "OR", "2026-08-21T16:05:00+00:00"),
    ("W-1807", "Fay@example.com", 31000, 4, "CA", "2026-08-25T09:45:00+00:00"),
    ("W-1808", "ana@example.com", -2400, 1, "CA", "2026-08-28T13:00:00+00:00"),
    ("W-1809", "gus@example.com", 7700, 1, "IL", "2026-08-30T20:20:00+00:00"),
]
SEPTEMBER = [
    ("W-1901", "ana@example.com", 1250, 1, "CA", "2026-09-01T08:12:00+00:00"),
    ("W-1902", "BEN@EXAMPLE.COM", 124000, 2, "NY", "2026-09-02T09:30:00+00:00"),
    ("W-1903", "cara@example.com", 725, 1, "TX", "2026-09-04T17:45:00+00:00"),
    ("W-1904", "Dev@Example.com", 310, 1, "WA", "2026-09-07T11:05:00+00:00"),
    ("W-1905", "erin@example.com", 8900, 3, "OR", "2026-09-09T19:02:00+00:00"),
    ("W-1906", "Cara@Example.com", 201540, 1, "TX", "2026-09-12T07:48:00+00:00"),
    ("W-1907", "ben@example.com", 1999, 1, "NY", "2026-09-15T12:00:00+00:00"),
    ("W-1908", "fay@example.com", 500, 4, "CA", "2026-09-18T16:31:00+00:00"),
    ("W-1909", "Gus@Example.com", -7700, 1, "IL", "2026-09-22T10:15:00+00:00"),
    ("W-1910", "hal@example.com", 5600, 2, "NV", "2026-09-26T15:50:00+00:00"),
    ("W-1911", "Erin@example.com", 1200, 1, "OR", "2026-09-29T18:25:00+00:00"),
]

path = Path("data/app.db")
conn = db.connect(path)
db.init_schema(conn)
with conn:
    conn.executemany(
        "INSERT INTO orders (order_id, email, amount_cents, quantity, region, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        AUGUST + SEPTEMBER,
    )
db.record_import(conn, "orders-2026-08.csv", 9, 9)
db.record_import(conn, "orders-2026-09.csv", 12, 11)
conn.close()
pipeline.run("data/orders.csv", path)
