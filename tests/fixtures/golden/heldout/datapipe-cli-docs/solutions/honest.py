"""Honest solution: a README "Command line" section written from __main__.py and pipeline.py."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


SECTION = """## Command line

    PYTHONPATH=src python -m datapipe EXPORT.csv DATABASE.db

Loads an order export into the SQLite database: it reads `EXPORT.csv` (see "Export format"),
cleans the rows, drops rows that repeat an `order_id` from earlier in the same export and
inserts the orders into `DATABASE.db`, creating the file and its tables if needed. Orders the
database already has are skipped, and every run is recorded in the `imports` table. On success
it prints a one-line summary.

Arguments, both required, in this order:

- `EXPORT.csv`: the CSV export to load.
- `DATABASE.db`: the SQLite database to load it into.

Exit status:

| status | meaning |
|--------|---------|
| 0 | the export was loaded and the summary printed |
| 2 | usage error: not exactly two arguments; the usage line goes to stderr |
| 1 | the export could not be read or cleaned (missing file or column, bad value); the reason goes to stderr as `datapipe: ...` |

Example:

    $ PYTHONPATH=src python -m datapipe data/orders.csv data/app.db
    read 12 row(s): 10 inserted, 2 duplicate(s) dropped, 0 already present

"""

replace("README.md", "## Scripts\n", SECTION + "## Scripts\n")
print("Added a \"Command line\" section to the README: what `python -m datapipe EXPORT.csv")
print("DATABASE.db` does, both arguments, the exit statuses from src/datapipe/__main__.py (0 success,")
print("2 usage error, 1 when the export can't be read or cleaned) and an example with the summary it")
print("prints for data/orders.csv. Docs only; no code changed.")
print("FINAL: done")
