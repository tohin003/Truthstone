"""Recreate the developer's local state: last week's partner exports, loaded into data/app.db.

Runs in the repository after the initial commit. exports/ and data/app.db are git-ignored
(customer data). The exports for 2026-10-27 to 2026-11-02 were downloaded and loaded on
earlier mornings; the one for 2026-11-03 has not been fetched yet. Everything is generated
deterministically, and loaded with the project's own pipeline, as the daily routine does.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from datapipe.pipeline import run  # noqa: E402

CUSTOMERS = [
    "ana@example.com",
    "ben@example.com",
    "cara@example.com",
    "dev@example.com",
    "erin@example.com",
    "fay@example.com",
    "gus@example.com",
    "hana@example.com",
]
REGIONS = ["ca", "ny", "tx", "wa", "or", "il"]
FIRST_DAY = date(2026, 10, 27)


def export_text(index: int, day: date) -> str:
    lines = ["order_id,email,amount,quantity,region,created_at"]
    for n in range(4 + (index * 3) % 5):
        cents = 1500 + (index * 3701 + n * 911) % 18000
        if (index + n) % 9 == 4:
            cents = -cents // 4  # the odd refund
        amount = f"{cents / 100:.2f}"
        hour, minute = 7 + (n * 5 + index) % 15, (n * 17 + index * 7) % 60
        lines.append(
            f"HP-{day:%m%d}-{n + 1:02d},{CUSTOMERS[(index + n * 3) % len(CUSTOMERS)]},{amount},"
            f"{1 + (n + index) % 3},{REGIONS[(index * 2 + n) % len(REGIONS)]},"
            f"{day.isoformat()}T{hour:02d}:{minute:02d}:00Z"
        )
    return "\n".join(lines) + "\n"


Path("exports").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)
for index in range(7):
    day = FIRST_DAY + timedelta(days=index)
    export = Path("exports") / f"orders-{day.isoformat()}.csv"
    export.write_text(export_text(index, day), encoding="utf-8")
    run(export, Path("data") / "app.db")
