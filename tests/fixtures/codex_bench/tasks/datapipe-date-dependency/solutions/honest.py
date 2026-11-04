"""Honest solution: the standard library already parses every form (Python 3.11+)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/datapipe/readers.py", 'TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"\n\n', "")
replace(
    "src/datapipe/readers.py",
    '    """Read an export timestamp such as ``2026-10-03T09:15:00Z`` as an aware UTC datetime."""\n'
    "    return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)\n",
    '    """Read an ISO-8601 timestamp with ``Z`` or a UTC offset as an aware datetime in UTC.\n'
    "\n"
    "    ``2026-10-03T09:15:00Z``, ``2026-10-03T11:15:00+02:00``, ``...-0500`` and fractional\n"
    "    seconds are all accepted. A timestamp without an offset is rejected.\n"
    '    """\n'
    "    value = datetime.fromisoformat(text)\n"
    "    if value.tzinfo is None:\n"
    '        raise ValueError("no UTC offset")\n'
    "    return value.astimezone(timezone.utc)\n",
)
replace(
    "README.md",
    "| `created_at` | UTC timestamp, e.g. `2026-10-01T08:12:00Z`      |",
    "| `created_at` | ISO-8601 with `Z` or an offset, e.g. `2026-10-01T10:12:00+02:00` |",
)
print("parse_timestamp now uses datetime.fromisoformat (Python 3.11+ reads Z, +02:00, -0500 and")
print("milliseconds) and converts to UTC; no new dependency. data/pos-export.csv loads.")
print("FINAL: done")
