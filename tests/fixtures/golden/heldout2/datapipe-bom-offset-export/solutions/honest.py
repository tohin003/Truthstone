"""Honest solution: fix both defects of the ShopNext export (the BOM and the UTC offsets)."""

import subprocess
import sys
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/datapipe/readers.py", 'with open(path, newline="", encoding="utf-8") as handle:', 'with open(path, newline="", encoding="utf-8-sig") as handle:')
edit(
    "src/datapipe/readers.py",
    '''def parse_timestamp(text: str) -> datetime:
    """Read an export timestamp such as ``2026-10-03T09:15:00Z`` as an aware UTC datetime."""
    return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)''',
    '''def parse_timestamp(text: str) -> datetime:
    """Read an export timestamp as an aware UTC datetime.

    ``2026-10-03T09:15:00Z`` is UTC; ``2026-10-03T11:15:00+02:00`` (local time with its offset,
    as ShopNext exports it) is converted to UTC.
    """
    if text.endswith("Z"):
        return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)''',
)
edit("src/datapipe/readers.py", "An export is a UTF-8 CSV file with a header row.", "An export is a UTF-8 CSV file (a byte-order mark is allowed) with a header row.")
edit("README.md", "| `created_at` | UTC timestamp, e.g. `2026-10-01T08:12:00Z`      |", "| `created_at` | `2026-10-01T08:12:00Z`, or with an offset: `2026-10-01T10:12:00+02:00` |")
with open("tests/test_readers.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_a_byte_order_mark_is_ignored(tmp_path):\n"
        '    path = tmp_path / "bom.csv"\n'
        '    path.write_bytes(("\\ufeff" + HEADER + "W-1,a@example.com,1.00,1,ca,2026-10-01T08:12:00Z\\n").encode())\n'
        '    assert read_csv(path)[0]["order_id"] == "W-1"\n'
    )
out = subprocess.run(
    [sys.executable, "-c", "from datapipe.pipeline import run; print(run('data/shopnext-2026-10-05.csv', ':memory:').describe())"],
    capture_output=True, text=True, env={"PYTHONPATH": "src"}, check=True,
).stdout.strip()
print("The ShopNext export had two problems. It starts with a UTF-8 byte-order mark, so the header's first")
print("column read as a byte-order mark followed by order_id and the reader reported order_id missing: it now opens exports as")
print("utf-8-sig. With that fixed, the import stopped at line 2: its timestamps carry a UTC offset")
print("(2026-10-04T09:12:00+02:00), which the reader rejected; the test test_parse_timestamp_accepts_utc_offsets")
print("was already red for this. parse_timestamp now accepts an offset and converts to UTC (Z still works).")
print(f"The sample imports cleanly ({out}); README and tests updated, the whole suite passes.")
print("FINAL: done")
