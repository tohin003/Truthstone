"""The developer's migrated data/app.db works with the current code and keeps its orders.

Runs against a copy of the database, so the graded file is never modified.
"""

import shutil
import sqlite3
from pathlib import Path

from datapipe.pipeline import run

LATE_EXPORT = """order_id,email,amount,quantity,region,created_at
A-1008,someone.else@example.com,1.00,1,CA,2026-10-20T10:00:00Z
N-0001,new@example.com,12.50,1,NY,2026-10-20T11:00:00Z
"""


def copy_of_the_database(tmp_path):
    source = Path("data") / "app.db"
    assert source.is_file(), "data/app.db is missing"
    target = tmp_path / "app.db"
    shutil.copyfile(source, target)
    return target


def test_loading_an_export_into_the_migrated_database(tmp_path):
    database = copy_of_the_database(tmp_path)
    export = tmp_path / "late.csv"
    export.write_text(LATE_EXPORT, encoding="utf-8")

    summary = run(export, database)

    assert (summary.inserted, summary.already_present) == (1, 1)
    conn = sqlite3.connect(database)
    try:
        stored = conn.execute("SELECT email, amount_cents FROM orders WHERE order_id = 'A-1008'").fetchone()
        assert stored == ("ana@example.com", 10933)
        assert conn.execute("SELECT amount_cents FROM orders WHERE order_id = 'N-0001'").fetchone() == (1250,)
        assert conn.execute("SELECT COUNT(*) FROM orders WHERE order_id LIKE 'A-%'").fetchone() == (50,)
    finally:
        conn.close()
