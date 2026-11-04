from datetime import datetime, timezone
from pathlib import Path

from datapipe.db import connect, daily_totals, totals_by_email
from datapipe.pipeline import run
from datapipe.readers import read_csv

# Saved from Excel by finance (see README, "Excel exports"); customer data replaced.
EXPORT = Path(__file__).parent / "fixtures" / "excel-export.csv"
UTC = timezone.utc


def test_reads_excel_export():
    rows = read_csv(EXPORT)
    assert [row["order_id"] for row in rows] == ["X-3001", "X-3002", "X-3003", "X-3004"]
    assert [row["email"] for row in rows] == [
        "ana@example.com",
        "Ben@Example.com",
        "cara@example.com",
        "dev@example.com",
    ]
    assert [row["quantity"] for row in rows] == [1, 2, 1, 3]
    assert [row["region"] for row in rows] == ["DE", "AT", "DE", "CH"]
    assert [row["created_at"] for row in rows] == [
        datetime(2026, 10, 5, 8, 12, tzinfo=UTC),
        datetime(2026, 10, 5, 9, 30, tzinfo=UTC),
        datetime(2026, 10, 5, 17, 45, tzinfo=UTC),
        datetime(2026, 10, 6, 10, 15, tzinfo=UTC),
    ]
    assert [row["notes"] for row in rows] == [
        "",
        "Gift wrap, please.\nLeave at reception.",
        "Refund: lid was cracked",
        'Customer wrote "urgent" twice',
    ]


def test_loads_excel_export(tmp_path):
    summary = run(EXPORT, tmp_path / "app.db")
    assert (summary.rows_read, summary.inserted) == (4, 4)
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {
            "ana@example.com": 1250,
            "ben@example.com": 124000,
            "cara@example.com": -399,
            "dev@example.com": 700,
        }
        assert daily_totals(conn) == {"2026-10-05": 124851, "2026-10-06": 700}
    finally:
        conn.close()
