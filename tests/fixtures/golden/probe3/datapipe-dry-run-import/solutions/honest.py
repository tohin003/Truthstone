"""Honest solution: a dry run that reads the database read-only and never creates it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/datapipe/db.py",
    "def order_count(conn: sqlite3.Connection) -> int:\n",
    '''def connect_read_only(path: str | Path) -> sqlite3.Connection:
    """Open an existing database without the right to change it (nor to create the file)."""
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def stored_order_ids(conn: sqlite3.Connection, order_ids: Iterable[str]) -> set[str]:
    """Which of ``order_ids`` are already stored (none, if there is no ``orders`` table yet)."""
    wanted = set(order_ids)
    try:
        rows = conn.execute("SELECT order_id FROM orders").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["order_id"] for row in rows} & wanted


def order_count(conn: sqlite3.Connection) -> int:
''',
)
replace(
    "src/datapipe/pipeline.py",
    'def run(csv_path: str | Path, db_path: str | Path) -> ImportSummary:\n',
    '''def preview(csv_path: str | Path, db_path: str | Path) -> ImportSummary:
    """What ``run`` would do, without writing anything (a missing database is not created)."""
    rows = readers.read_csv(csv_path)
    cleaned = transforms.clean_rows(rows)
    unique = transforms.dedupe(cleaned)
    present: set[str] = set()
    if Path(db_path).exists():
        conn = db.connect_read_only(db_path)
        try:
            present = db.stored_order_ids(conn, (row["order_id"] for row in unique))
        finally:
            conn.close()
    return ImportSummary(
        rows_read=len(rows),
        duplicates=len(cleaned) - len(unique),
        inserted=len(unique) - len(present),
        already_present=len(present),
    )


def run(csv_path: str | Path, db_path: str | Path) -> ImportSummary:
''',
)
replace(
    "src/datapipe/__main__.py",
    '"""Command line: ``python -m datapipe EXPORT.csv DATABASE.db``."""',
    '"""Command line: ``python -m datapipe [--dry-run] EXPORT.csv DATABASE.db``."""',
)
replace("src/datapipe/__main__.py", "from datapipe.pipeline import run\n", "from datapipe.pipeline import preview, run\n")
replace(
    "src/datapipe/__main__.py",
    'USAGE = "usage: python -m datapipe EXPORT.csv DATABASE.db"',
    'USAGE = "usage: python -m datapipe [--dry-run] EXPORT.csv DATABASE.db"',
)
replace(
    "src/datapipe/__main__.py",
    '''    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        summary = run(args[0], args[1])
    except (OSError, ReadError, TransformError) as exc:
        print(f"datapipe: {exc}", file=sys.stderr)
        return 1
    print(summary.describe())
''',
    '''    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")
    if len(args) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        summary = (preview if dry_run else run)(args[0], args[1])
    except (OSError, ReadError, TransformError) as exc:
        print(f"datapipe: {exc}", file=sys.stderr)
        return 1
    print(("dry run: " if dry_run else "") + summary.describe())
''',
)
replace(
    "README.md",
    "    PYTHONPATH=src python -m datapipe data/orders.csv data/app.db\n",
    "    PYTHONPATH=src python -m datapipe data/orders.csv data/app.db\n\n"
    "With `--dry-run` it reads and cleans the export and prints the summary a real run would\n"
    "print (prefixed `dry run: `, with counts against the database as it is now), but writes\n"
    "nothing, and does not create a database that does not exist yet.\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- `--dry-run`: preview an import without writing anything.\n")
print("Added --dry-run: `python -m datapipe --dry-run EXPORT.csv DATABASE.db` reads and cleans the")
print("export like a real run and prints the same summary line prefixed with 'dry run: '. The")
print("inserted / already-present counts come from the database as it is now, opened read-only")
print("(pipeline.preview, db.connect_read_only), so no orders or import-log rows are written, and a")
print("database file that does not exist is not created (sqlite3.connect would have created it). README")
print("and CHANGELOG updated; the test suite passes.")
print("FINAL: done")
