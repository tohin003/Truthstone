"""The import summary means what the README says: rows_read counts every non-blank data row,
and inserted + duplicates + already_present == rows_read for every import that completes."""

from datapipe.db import connect, order_count
from datapipe.pipeline import run
from datapipe.readers import ReadError
from datapipe.transforms import TransformError

HEADER = "order_id,email,amount,quantity,region,created_at\n"
GOOD = (
    "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
    "W-2,ben@example.com,40.00,2,ny,2026-10-01T09:30:00Z\n"
    "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
    "\n"
    "W-3,cara@example.com,-2.50,1,tx,2026-10-02T11:05:00Z\n"
)


def write(tmp_path, body, name="orders.csv"):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_a_clean_export_is_counted_as_documented(tmp_path):
    export, database = write(tmp_path, GOOD), tmp_path / "app.db"
    first = run(export, database)
    assert (first.rows_read, first.duplicates, first.inserted, first.already_present) == (4, 1, 3, 0)
    again = run(export, database)
    assert (again.rows_read, again.duplicates, again.inserted, again.already_present) == (4, 1, 0, 3)


def _check_completed_import(export, database, data_rows):
    try:
        summary = run(export, database)
    except (ReadError, TransformError):
        conn = connect(database)
        try:
            stored = conn.execute("SELECT name FROM sqlite_master WHERE name = 'orders'").fetchone()
            assert stored is None or order_count(conn) == 0, "a stopped import must load nothing"
        finally:
            conn.close()
        return
    conn = connect(database)
    try:
        stored = order_count(conn)
    finally:
        conn.close()
    assert summary.rows_read == data_rows, "rows_read counts every non-blank data row"
    assert summary.already_present == 0, "the database was empty"
    assert summary.inserted == stored, "inserted is what this import stored"
    assert summary.inserted + summary.duplicates + summary.already_present == summary.rows_read


def test_an_export_with_a_bad_quantity(tmp_path):
    body = GOOD + "W-4,dev@example.com,9.99,two,wa,2026-10-02T12:00:00Z\n"
    _check_completed_import(write(tmp_path, body), tmp_path / "app.db", 5)


def test_an_export_with_a_bad_amount(tmp_path):
    body = "W-7,erin@example.com,12.5O,1,or,2026-10-03T08:00:00Z\n" + GOOD
    _check_completed_import(write(tmp_path, body), tmp_path / "app.db", 5)
