"""Write every order in the reporting database to a CSV extract for finance.

    python scripts/extract.py DATABASE.db TARGET.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datapipe.db import connect  # noqa: E402

COLUMNS = ("order_id", "email", "amount_cents", "region", "created_at")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python scripts/extract.py DATABASE.db TARGET.csv", file=sys.stderr)
        return 2
    database, target = args
    conn = connect(database)
    try:
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM orders ORDER BY order_id").fetchall()
    finally:
        conn.close()
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(tuple(row) for row in rows)
    print(f"extract: wrote {len(rows)} order(s) to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
