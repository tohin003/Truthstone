"""Download one day's order export from the partner (Harbor & Pine) into exports/.

    python scripts/fetch_export.py 2026-11-03     # -> exports/orders-2026-11-03.csv

The partner publishes each day's orders the following morning. A failed download writes
nothing, so a half-downloaded export can never be loaded by mistake.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

EXPORT_URL = "https://exports.harborpine.example/orders/{day}.csv"
EXPORT_DIR = Path("exports")
TIMEOUT = 30


def export_url(day: date) -> str:
    return EXPORT_URL.format(day=day.isoformat())


def export_path(day: date, directory: Path = EXPORT_DIR) -> Path:
    return directory / f"orders-{day.isoformat()}.csv"


def download(day: date, directory: Path = EXPORT_DIR) -> Path:
    """Fetch the export for ``day`` into ``directory`` and return its path."""
    request = urllib.request.Request(export_url(day), headers={"User-Agent": "datapipe-fetch/0.3"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read()
    target = export_path(day, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(body)
    partial.replace(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download one day's partner export into exports/.")
    parser.add_argument("day", type=date.fromisoformat, help="the export's date, YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        path = download(args.day)
    except (urllib.error.URLError, OSError) as exc:
        print(f"fetch_export: could not download {export_url(args.day)}: {exc}", file=sys.stderr)
        return 1
    print(f"fetch_export: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
