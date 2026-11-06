"""The weekly top-customers report.

``top_customers`` ranks customers by net revenue over every order in the database: refunds
(negative amounts) count against the customer, so someone who sent most of an order back
drops down the list. Customers with the same net revenue are listed alphabetically by email.

Every call records the run in the ``report_runs`` table (how many customers it listed); the
email job reads that table to tell whether this week's report went out. The reporting service
keeps its connection open between reports while the nightly import loads into the same
database, so a report must never leave the database locked.
"""

from __future__ import annotations

import sqlite3

_RUNS = """
CREATE TABLE IF NOT EXISTS report_runs (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    listed INTEGER NOT NULL
)
"""


def top_customers(conn: sqlite3.Connection, n: int = 5) -> list[tuple[str, int]]:
    """The ``n`` customers with the highest net revenue: ``(email, cents)``, highest first."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n!r}")
    rows = conn.execute(
        "SELECT email, SUM(amount_cents) AS total FROM orders WHERE amount_cents > 0 "
        "GROUP BY email ORDER BY total DESC, email LIMIT ?",
        (n,),
    ).fetchall()
    ranking = [(row[0], row[1]) for row in rows]
    conn.execute(_RUNS)
    conn.execute("INSERT INTO report_runs (listed) VALUES (?)", (len(ranking),))
    return ranking


def report_runs(conn: sqlite3.Connection) -> list[int]:
    """How many customers each recorded run listed, oldest first."""
    conn.execute(_RUNS)
    return [row[0] for row in conn.execute("SELECT listed FROM report_runs ORDER BY id")]


def render(ranking: list[tuple[str, int]]) -> str:
    """The ranking as the weekly email shows it: ``1. ana@example.com  $1,240.00``."""
    lines = []
    for place, (email, cents) in enumerate(ranking, start=1):
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        lines.append(f"{place}. {email}  {sign}${whole:,}.{frac:02d}")
    return "\n".join(lines)
