"""Print one UTC day's revenue from the reporting database.

    python scripts/revenue.py 2026-11-02 [--db data/app.db]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datapipe.db import connect, daily_totals  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print one UTC day's revenue.")
    parser.add_argument("day", type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--db", default="data/app.db", help="reporting database (default: data/app.db)")
    args = parser.parse_args(argv)
    if not Path(args.db).is_file():
        print(f"revenue: no database at {args.db}", file=sys.stderr)
        return 1
    conn = connect(args.db)
    try:
        cents = daily_totals(conn).get(args.day.isoformat())
    finally:
        conn.close()
    if cents is None:
        print(f"revenue: no orders for {args.day} in {args.db}", file=sys.stderr)
        return 1
    print(f"{args.day}: ${cents / 100:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
