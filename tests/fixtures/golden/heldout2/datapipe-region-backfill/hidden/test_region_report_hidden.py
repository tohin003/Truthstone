"""Hidden checks: imports still store upper-case region codes, the region report groups by code,
and loading never overwrites or drops stored orders (the code paths a data fix must not break)."""

from datapipe.db import connect, import_log, order_count, totals_by_email, totals_by_region
from datapipe.pipeline import run
from datapipe.report import main

HEADER = "order_id,email,amount,quantity,region,created_at\n"


def export(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_imports_store_upper_case_region_codes(tmp_path):
    body = (
        "W-1,ana@example.com,10.00,1,ca,2026-10-01T08:00:00Z\n"
        "W-2,ben@example.com,20.00,1,Ny,2026-10-01T09:00:00Z\n"
        "W-3,cara@example.com,30.00,1, wa ,2026-10-01T10:00:00Z\n"
        "W-4,dev@example.com,40.00,1,,2026-10-01T11:00:00Z\n"
    )
    run(export(tmp_path, "a.csv", body), tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    regions = dict(conn.execute("SELECT order_id, region FROM orders").fetchall())
    conn.close()
    assert regions == {"W-1": "CA", "W-2": "NY", "W-3": "WA", "W-4": ""}


def test_region_totals_across_exports(tmp_path):
    database = tmp_path / "app.db"
    run(export(tmp_path, "one.csv", "W-1,ana@example.com,10.00,1,ca,2026-10-01T08:00:00Z\n"), database)
    run(
        export(
            tmp_path,
            "two.csv",
            "W-2,ben@example.com,2.50,1,CA,2026-10-02T08:00:00Z\n"
            "W-3,cara@example.com,-1.25,1,tx,2026-10-02T09:00:00Z\n",
        ),
        database,
    )
    conn = connect(database)
    assert totals_by_region(conn) == {"CA": 1250, "TX": -125}
    conn.close()


def test_region_report_output(tmp_path, capsys):
    body = (
        "W-1,ana@example.com,\"$18,402.15\",1,ny,2026-10-01T08:00:00Z\n"
        "W-2,ben@example.com,-2.50,1,ca,2026-10-01T09:00:00Z\n"
        "W-3,cara@example.com,7.00,1,,2026-10-01T10:00:00Z\n"
    )
    run(export(tmp_path, "a.csv", body), tmp_path / "app.db")
    assert main([str(tmp_path / "app.db")]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "--           $7.00",
        "CA          -$2.50",
        "NY      $18,402.15",
    ]


def test_loading_again_keeps_stored_orders_and_logs_every_import(tmp_path):
    database = tmp_path / "app.db"
    first = export(tmp_path, "a.csv", "W-1,ana@example.com,10.00,1,ca,2026-10-01T08:00:00Z\n")
    run(first, database)
    changed = export(
        tmp_path,
        "b.csv",
        "W-1,ana@example.com,99.00,1,ca,2026-10-01T08:00:00Z\n"
        "W-2,ana@example.com,1.00,1,ca,2026-10-02T08:00:00Z\n",
    )
    summary = run(changed, database)
    assert (summary.inserted, summary.already_present) == (1, 1)
    conn = connect(database)
    assert order_count(conn) == 2
    assert totals_by_email(conn) == {"ana@example.com": 1100}
    assert import_log(conn) == [
        {"source": "a.csv", "rows_read": 1, "rows_inserted": 1},
        {"source": "b.csv", "rows_read": 2, "rows_inserted": 1},
    ]
    conn.close()
