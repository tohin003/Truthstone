import pytest

from datapipe.__main__ import main
from datapipe.db import connect, import_log, order_count, totals_by_email
from datapipe.pipeline import run
from datapipe.readers import ReadError

EXPORT = """order_id,email,amount,quantity,region,created_at
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-2,BEN@example.com,$40.00,2,ny,2026-10-01T09:30:00Z
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-3,ana@example.com,-2.50,1,ca,2026-10-02T11:05:00Z
"""


def write_export(tmp_path, text=EXPORT):
    path = tmp_path / "orders.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_run_loads_an_export(tmp_path):
    summary = run(write_export(tmp_path), tmp_path / "app.db")
    assert (summary.rows_read, summary.duplicates, summary.inserted, summary.already_present) == (4, 1, 3, 0)
    conn = connect(tmp_path / "app.db")
    assert totals_by_email(conn) == {"ana@example.com": 1000, "ben@example.com": 4000}
    assert import_log(conn) == [{"source": "orders.csv", "rows_read": 4, "rows_inserted": 3}]
    conn.close()


def test_the_summary_counts_add_up_to_rows_read(tmp_path):
    export, database = write_export(tmp_path), tmp_path / "app.db"
    for summary in (run(export, database), run(export, database)):
        assert summary.inserted + summary.duplicates + summary.already_present == summary.rows_read


def test_a_bad_row_stops_the_import(tmp_path):
    bad = write_export(tmp_path, EXPORT + "W-4,ana@example.com,1.00,two,ca,2026-10-02T12:00:00Z\n")
    with pytest.raises(ReadError, match="line 6"):
        run(bad, tmp_path / "app.db")


def test_loading_the_same_export_twice(tmp_path):
    export, database = write_export(tmp_path), tmp_path / "app.db"
    run(export, database)
    again = run(export, database)
    assert (again.inserted, again.already_present) == (0, 3)
    conn = connect(database)
    assert order_count(conn) == 3
    conn.close()


def test_cli(tmp_path, capsys):
    assert main([str(write_export(tmp_path)), str(tmp_path / "app.db")]) == 0
    assert "3 inserted" in capsys.readouterr().out


def test_cli_usage(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_cli_reports_a_bad_export(tmp_path, capsys):
    bad = write_export(tmp_path, "order_id,email\nW-1,a@example.com\n")
    assert main([str(bad), str(tmp_path / "app.db")]) == 1
    assert "missing column" in capsys.readouterr().err
