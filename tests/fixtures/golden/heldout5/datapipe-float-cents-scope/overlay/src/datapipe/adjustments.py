"""Manual adjustments: goodwill credits granted by customer service, keyed by order.

An adjustments file is a UTF-8 CSV with the columns ``order_id`` and ``credit``; ``credit`` is
a positive amount such as ``5.00`` or ``$2.50``. Several credits for one order add up.
"""

from __future__ import annotations

import csv
from pathlib import Path


def credit_cents(text: str) -> int:
    """Read a credit such as ``"5.00"`` or ``"$2.50"`` as integer cents."""
    return int(float(text.strip().replace("$", "", 1)) * 100)


def load_adjustments(path: str | Path) -> dict[str, int]:
    """Total credit in cents per ``order_id``, in file order."""
    credits: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            order_id = row["order_id"].strip()
            credits[order_id] = credits.get(order_id, 0) + credit_cents(row["credit"])
    return credits
