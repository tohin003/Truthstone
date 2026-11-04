"""The documented rule: every pipeline run appends one import-log row, including runs that insert nothing."""

from datapipe.__main__ import main
from datapipe.db import connect, import_log, order_count
from datapipe.pipeline import run

EXPORT = """order_id,email,amount,quantity,region,created_at
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-2,BEN@example.com,$40.00,2,ny,2026-10-01T09:30:00Z
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-3,ana@example.com,-2.50,1,ca,2026-10-02T11:05:00Z
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def log(database):
    conn = connect(database)
    try:
        return import_log(conn)
    finally:
        conn.close()


def test_a_rerun_of_an_unchanged_export_is_logged_with_zero_inserted(tmp_path):
    export, database = write(tmp_path, "orders.csv", EXPORT), tmp_path / "app.db"
    run(export, database)
    again = run(export, database)
    assert (again.inserted, again.already_present) == (0, 3)
    assert log(database) == [
        {"source": "orders.csv", "rows_read": 4, "rows_inserted": 3},
        {"source": "orders.csv", "rows_read": 4, "rows_inserted": 0},
    ]


def test_every_run_is_logged_hourly_reruns_included(tmp_path):
    export, database = write(tmp_path, "orders.csv", EXPORT), tmp_path / "app.db"
    for _ in range(3):
        run(export, database)
    assert [entry["rows_inserted"] for entry in log(database)] == [3, 0, 0]


def test_an_export_of_orders_already_loaded_is_still_logged(tmp_path):
    database = tmp_path / "app.db"
    run(write(tmp_path, "orders.csv", EXPORT), database)
    run(write(tmp_path, "orders-copy.csv", EXPORT), database)
    assert log(database)[-1] == {"source": "orders-copy.csv", "rows_read": 4, "rows_inserted": 0}


def test_an_empty_export_is_logged(tmp_path):
    database = tmp_path / "app.db"
    run(write(tmp_path, "empty.csv", "order_id,email,amount,quantity,region,created_at\n"), database)
    assert log(database) == [{"source": "empty.csv", "rows_read": 0, "rows_inserted": 0}]


def test_the_command_line_logs_a_rerun_too(tmp_path, capsys):
    export, database = write(tmp_path, "orders.csv", EXPORT), tmp_path / "app.db"
    assert main([str(export), str(database)]) == 0
    assert main([str(export), str(database)]) == 0
    assert "0 inserted" in capsys.readouterr().out
    assert len(log(database)) == 2
    conn = connect(database)
    assert order_count(conn) == 3
    conn.close()
