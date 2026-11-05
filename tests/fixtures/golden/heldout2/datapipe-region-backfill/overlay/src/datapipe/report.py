"""Revenue per region: ``python -m datapipe.report DATABASE.db``.

Prints one line per region code, in code order, with the revenue in dollars::

    CA      $18,402.15
    NY       $9,310.00

Orders without a region are listed as ``--``. The database is only read, never created.
"""

from __future__ import annotations

import sys
from pathlib import Path

from datapipe import db

USAGE = "usage: python -m datapipe.report DATABASE.db"


def format_cents(cents: int) -> str:
    """``1840215`` -> ``"$18,402.15"``; refunds keep their sign: ``-250`` -> ``"-$2.50"``."""
    dollars, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}${dollars:,}.{rest:02d}"


def region_lines(conn) -> list[str]:
    return [
        f"{region or '--':<4}{format_cents(total):>14}" for region, total in db.totals_by_region(conn).items()
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(f"report: no database at {path}", file=sys.stderr)
        return 1
    conn = db.connect(path)
    try:
        for line in region_lines(conn):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
