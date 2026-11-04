"""The orders column is total_cents everywhere: schema, rows, queries, the report and the scripts."""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from datapipe.__main__ import main
from datapipe.db import connect, daily_totals, init_schema, insert_orders, order_count, totals_by_email
from datapipe.pipeline import run
from datapipe.transforms import clean_rows, group_totals

UTC = timezone.utc
EXPORT = """order_id,email,amount,quantity,region,created_at
T-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
T-2,ben@example.com,"$1,240.00",2,ny,2026-10-01T09:30:00Z
T-3,ana@example.com,7.50,1,ca,2026-10-02T11:05:00Z
T-4,cara@example.com,-2.00,1,tx,2026-10-02T12:00:00Z
T-5,dev@example.com,30.00,1,ny,2026-10-03T08:00:00Z
"""


@pytest.fixture
def database(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(EXPORT, encoding="utf-8")
    path = tmp_path / "app.db"
    assert run(export, path).inserted == 5
    return path


def test_the_schema_has_total_cents_and_no_amount_cents(tmp_path):
    conn = connect(tmp_path / "fresh.db")
    try:
        init_schema(conn)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
    finally:
        conn.close()
    assert "total_cents" in columns
    assert "amount_cents" not in columns


def test_cleaned_rows_carry_total_cents():
    [row] = clean_rows([{"order_id": "W-1", "email": "A@example.com", "amount": "$3.99", "region": "CA"}])
    assert row["total_cents"] == 399
    assert "amount_cents" not in row


def test_storing_and_summing_rows(tmp_path):
    conn = connect(tmp_path / "app.db")
    try:
        init_schema(conn)
        rows = [
            {"order_id": "R-1", "email": "a@example.com", "total_cents": 500, "quantity": 1, "region": "CA",
             "created_at": datetime(2026, 10, 1, 10, 0, tzinfo=UTC)},
            {"order_id": "R-2", "email": "b@example.com", "total_cents": 250, "quantity": 1, "region": "NY",
             "created_at": datetime(2026, 10, 2, 10, 0, tzinfo=UTC)},
        ]
        assert insert_orders(conn, rows) == 2
        assert totals_by_email(conn) == {"a@example.com": 500, "b@example.com": 250}
        assert daily_totals(conn) == {"2026-10-01": 500, "2026-10-02": 250}
    finally:
        conn.close()
    assert group_totals(rows, "region") == {"CA": 500, "NY": 250}


def test_loading_an_export(database):
    conn = connect(database)
    try:
        assert order_count(conn) == 5
        assert totals_by_email(conn)["ana@example.com"] == 2000
    finally:
        conn.close()


def test_the_report_command(database, capsys):
    assert main(["report", str(database)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "region    orders       revenue",
        "NY             2      1,270.00",
        "CA             2         20.00",
        "TX             1         -2.00",
    ]


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="needs the sqlite3 command-line shell")
def test_the_top_customers_script(database):
    proc = subprocess.run(
        ["sh", str(Path("scripts") / "top_customers.sh"), str(database), "2"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["ben@example.com 1240.00", "dev@example.com 30.00"]


def test_the_import_command_still_works(tmp_path, capsys):
    export = tmp_path / "orders.csv"
    export.write_text(EXPORT, encoding="utf-8")
    assert main([str(export), str(tmp_path / "cli.db")]) == 0
    assert "5 inserted" in capsys.readouterr().out
    assert main([]) == 2
