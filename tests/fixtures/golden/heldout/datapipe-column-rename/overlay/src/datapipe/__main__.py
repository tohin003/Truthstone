"""Command line: ``python -m datapipe EXPORT.csv DATABASE.db`` or ``python -m datapipe report DATABASE.db``."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from datapipe.db import connect
from datapipe.pipeline import run
from datapipe.readers import ReadError
from datapipe.transforms import TransformError

USAGE = "usage: python -m datapipe EXPORT.csv DATABASE.db\n       python -m datapipe report DATABASE.db"

# The revenue report's query lives with the other SQL the team edits by hand.
REPORT_SQL = Path(__file__).resolve().parents[2] / "scripts" / "report.sql"


def report(database: str) -> int:
    """Print revenue per region, as computed by scripts/report.sql."""
    if not Path(database).is_file():
        print(f"datapipe: no database at {database}", file=sys.stderr)
        return 1
    conn = connect(database)
    try:
        rows = conn.execute(REPORT_SQL.read_text(encoding="utf-8")).fetchall()
    except sqlite3.Error as exc:
        print(f"datapipe: report failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"{'region':<8}{'orders':>8}{'revenue':>14}")
    for row in rows:
        print(f"{row['region'] or '-':<8}{row['orders']:>8}{row['revenue_cents'] / 100:>14,.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["report"]:
        if len(args) != 2:
            print(USAGE, file=sys.stderr)
            return 2
        return report(args[1])
    if len(args) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        summary = run(args[0], args[1])
    except (OSError, ReadError, TransformError) as exc:
        print(f"datapipe: {exc}", file=sys.stderr)
        return 1
    print(summary.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
