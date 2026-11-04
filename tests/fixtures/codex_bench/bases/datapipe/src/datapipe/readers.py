"""Reading order exports.

An export is a UTF-8 CSV file with a header row. ``read_csv`` returns one dict per data
row. Known columns are converted by their entry in ``COLUMNS``; any other column is kept
as text. Surrounding whitespace is stripped from every value, and blank rows are skipped.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

REQUIRED = ("order_id", "email", "amount", "created_at")


class ReadError(ValueError):
    """An export could not be read. The message names the line and the column."""


def parse_timestamp(text: str) -> datetime:
    """Read an export timestamp such as ``2026-10-03T09:15:00Z`` as an aware UTC datetime."""
    return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def parse_quantity(text: str) -> int:
    """A whole number of at least one; a blank cell means one."""
    if not text:
        return 1
    quantity = int(text)
    if quantity < 1:
        raise ValueError("must be at least 1")
    return quantity


COLUMNS: dict[str, Callable[[str], Any]] = {
    "order_id": str,
    "email": str,
    "amount": str,  # kept as text; transforms.parse_amount turns it into cents
    "quantity": parse_quantity,
    "region": str.upper,
    "created_at": parse_timestamp,
}


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    """Read the export at ``path``. Raises ``ReadError`` for a missing column or a bad value."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            raise ReadError(f"{path}: missing column(s): {', '.join(missing)}")
        rows = []
        for raw in reader:
            if not any(isinstance(value, str) and value.strip() for value in raw.values()):
                continue
            rows.append(_convert(raw, reader.line_num))
    return rows


def _convert(raw: dict[str | None, Any], line: int) -> dict[str, Any]:
    if None in raw:
        raise ReadError(f"line {line}: more values than columns")
    row: dict[str, Any] = {}
    for name, value in raw.items():
        text = (value or "").strip()
        convert = COLUMNS.get(name, str)
        try:
            row[name] = convert(text)
        except ValueError as exc:
            raise ReadError(f"line {line}: bad {name} {text!r}: {exc}") from exc
    return row
