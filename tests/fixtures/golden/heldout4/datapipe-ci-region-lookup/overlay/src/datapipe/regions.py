"""Region names for reports.

Exports carry two-letter region codes (``CA``, ``NY``); reports show names. The names come from
the lookup table ``data/regions.csv`` (columns ``code,name``), which lives in the repository.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

REGIONS_CSV = Path(__file__).resolve().parents[2] / "data" / "regions.csv"


def region_names(path: str | Path = REGIONS_CSV) -> dict[str, str]:
    """Region code -> display name, e.g. ``{"CA": "California"}``."""
    with open(path, newline="", encoding="utf-8") as handle:
        return {row["code"].strip().upper(): row["name"].strip() for row in csv.DictReader(handle)}


def totals_by_region(conn: sqlite3.Connection, names: dict[str, str] | None = None) -> dict[str, int]:
    """Total ``amount_cents`` per region, keyed by display name; an unknown code is shown as is."""
    names = region_names() if names is None else names
    totals: dict[str, int] = {}
    rows = conn.execute(
        "SELECT region, SUM(amount_cents) AS total FROM orders GROUP BY region ORDER BY region"
    )
    for row in rows:
        label = names.get(row["region"], row["region"] or "(none)")
        totals[label] = totals.get(label, 0) + row["total"]
    return totals
