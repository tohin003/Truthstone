"""Loading new exports into a reporting database that an earlier release created.

Production keeps one long-lived reporting database: each deploy appends the day's export to
it and nothing ever rebuilds it, so every release has to load into a database made by the
release before it.
"""

from datapipe.db import connect, import_log, order_count, totals_by_email
from datapipe.pipeline import run

EXPORT = """order_id,email,amount,quantity,region,created_at
L-1001,ana@example.com,12.50,1,ca,2026-09-01T08:00:00Z
N-2001,ana@example.com,20.00,1,ca,2026-10-07T09:00:00Z
N-2002,erin@example.com,$5.10,2,or,2026-10-07T10:30:00Z
"""


def load(tmp_path, database):
    export = tmp_path / "orders-2026-10-07.csv"
    export.write_text(EXPORT, encoding="utf-8")
    return run(export, database)


def test_import_into_a_legacy_database(legacy_db, tmp_path):
    summary = load(tmp_path, legacy_db)
    assert (summary.rows_read, summary.inserted, summary.already_present) == (3, 2, 1)
    conn = connect(legacy_db)
    try:
        assert order_count(conn) == 7
        totals = totals_by_email(conn)
        assert totals["ana@example.com"] == 1250 - 250 + 2000
        assert totals["erin@example.com"] == 510
        assert totals["dev@example.com"] == 19999
    finally:
        conn.close()


def test_legacy_import_log_is_kept(legacy_db, tmp_path):
    load(tmp_path, legacy_db)
    conn = connect(legacy_db)
    try:
        assert import_log(conn) == [
            {"source": "orders-2026-09-01.csv", "rows_read": 2, "rows_inserted": 2},
            {"source": "orders-2026-09-02.csv", "rows_read": 4, "rows_inserted": 3},
            {"source": "orders-2026-10-07.csv", "rows_read": 3, "rows_inserted": 2},
        ]
    finally:
        conn.close()
