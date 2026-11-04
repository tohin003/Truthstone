"""Command line: ``python -m datapipe EXPORT.csv [DATABASE.db]``.

Without a database argument, the export loads into ``[database] path`` from your datapipe.toml.
"""

from __future__ import annotations

import sys

from datapipe.pipeline import run
from datapipe.readers import ReadError
from datapipe.settings import SettingsError, load_settings
from datapipe.transforms import TransformError

USAGE = "usage: python -m datapipe EXPORT.csv [DATABASE.db]"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        database = args[1] if len(args) == 2 else load_settings().database
        summary = run(args[0], database)
    except (OSError, ReadError, TransformError, SettingsError) as exc:
        print(f"datapipe: {exc}", file=sys.stderr)
        return 1
    print(summary.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
