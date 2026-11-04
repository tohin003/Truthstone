"""Command line: ``python -m datapipe EXPORT.csv DATABASE.db``."""

from __future__ import annotations

import sys

from datapipe.pipeline import run
from datapipe.readers import ReadError
from datapipe.transforms import TransformError

USAGE = "usage: python -m datapipe EXPORT.csv DATABASE.db"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
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
