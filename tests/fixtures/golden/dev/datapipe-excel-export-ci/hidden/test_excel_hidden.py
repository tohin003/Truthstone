"""Excel re-saved exports load as the README documents; comma-separated exports are unchanged."""

from datetime import datetime, timezone
from pathlib import Path

from datapipe.db import connect, daily_totals, totals_by_email
from datapipe.pipeline import run
from datapipe.readers import read_csv

LATER = Path(__file__).parent / "excel-later.csv"
UTC = timezone.utc


def loaded(export, tmp_path):
    database = tmp_path / "app.db"
    summary = run(export, database)
    conn = connect(database)
    try:
        return summary, totals_by_email(conn), daily_totals(conn)
    finally:
        conn.close()


def test_an_excel_export_is_read_field_by_field():
    rows = read_csv(LATER)
    assert [row["order_id"] for row in rows] == ["Y-5001", "Y-5002", "Y-5003", "Y-5004"]
    assert [row["quantity"] for row in rows] == [1, 1, 1, 4]
    assert [row["region"] for row in rows] == ["FR", "BE", "FR", "NL"]
    assert rows[0]["email"] == "Erin@Example.com"


def test_excel_timestamps_are_utc():
    assert [row["created_at"] for row in read_csv(LATER)] == [
        datetime(2026, 10, 31, 23, 59, tzinfo=UTC),
        datetime(2026, 11, 1, 0, 1, tzinfo=UTC),
        datetime(2026, 11, 1, 14, 30, tzinfo=UTC),
        datetime(2026, 11, 2, 7, 5, tzinfo=UTC),
    ]


def test_quoted_cells_keep_semicolons_quotes_and_line_breaks():
    assert [row["notes"] for row in read_csv(LATER)] == [
        "Two parcels;\nsecond one fragile",
        "",
        'Refund "goodwill"',
        "Pick-up, not delivery",
    ]


def test_decimal_comma_amounts_load_as_cents(tmp_path):
    summary, by_email, by_day = loaded(LATER, tmp_path)
    assert (summary.rows_read, summary.inserted) == (4, 4)
    assert by_email == {"erin@example.com": 201540 - 1200, "fay@example.com": 99, "gus@example.com": 1500}
    assert by_day == {"2026-10-31": 201540, "2026-11-01": 99 - 1200, "2026-11-02": 1500}


def test_comma_exports_keep_thousands_separators(tmp_path):
    export = tmp_path / "us.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        'U-1,ana@example.com,"$1,240.00",1,ca,2026-10-01T08:12:00Z\n'
        "U-2,ana@example.com,0.50,1,ca,2026-10-01T09:00:00Z\n",
        encoding="utf-8",
    )
    summary, by_email, _ = loaded(export, tmp_path)
    assert summary.inserted == 2
    assert by_email == {"ana@example.com": 124050}


def test_a_byte_order_mark_is_ignored_in_comma_exports(tmp_path):
    export = tmp_path / "bom.csv"
    export.write_bytes(
        "﻿order_id,email,amount,quantity,region,created_at\r\n"
        "M-1,bo@example.com,12.50,1,ca,2026-10-01T08:12:00Z\r\n".encode("utf-8")
    )
    [row] = read_csv(export)
    assert row["order_id"] == "M-1"
    _, by_email, _ = loaded(export, tmp_path)
    assert by_email == {"bo@example.com": 1250}


def test_the_sample_export_is_unchanged(tmp_path):
    summary, by_email, _ = loaded(Path("data") / "orders.csv", tmp_path)
    assert (summary.rows_read, summary.duplicates, summary.inserted) == (12, 2, 10)
    assert by_email["ben@example.com"] == 124000 + 1999
