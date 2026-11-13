"""read_csv(decimal_comma=True) rewrites European amounts into the pipeline's usual form."""

from datetime import datetime, timezone

from datapipe.pipeline import run
from datapipe.db import connect, totals_by_email
from datapipe.readers import read_csv
from datapipe.transforms import clean_rows

HEADER = "order_id,email,amount,quantity,region,created_at\n"


def write(tmp_path, body, name="export.csv"):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_the_requests_examples_are_rewritten(tmp_path):
    path = write(
        tmp_path,
        'V-1,a@example.at,"€12,50",1,at,2026-11-02T08:40:00Z\n'
        'V-2,b@example.at,"1.240,00",2,at,2026-11-02T10:05:00Z\n'
        'V-3,a@example.at,"-3,50",1,at,2026-11-02T12:30:00Z\n',
    )
    assert [row["amount"] for row in read_csv(path, decimal_comma=True)] == ["12.50", "1240.00", "-3.50"]


def test_european_amounts_reach_the_pipeline_as_cents(tmp_path):
    path = write(
        tmp_path,
        'V-1,a@example.at,"€12,50",1,at,2026-11-02T08:40:00Z\n'
        'V-2,b@example.at,"1.240,00",2,at,2026-11-02T10:05:00Z\n'
        'V-3,a@example.at,"-3,50",1,at,2026-11-02T12:30:00Z\n'
        'V-4,c@example.at,"€89,90",3,at,2026-11-03T09:15:00Z\n'
        "V-5,b@example.at,7,1,at,2026-11-03T16:00:00Z\n"
        'V-6,c@example.at,"12.345,6",1,at,2026-11-03T17:00:00Z\n',
    )
    cleaned = clean_rows(read_csv(path, decimal_comma=True))
    assert [row["amount_cents"] for row in cleaned] == [1250, 124000, -350, 8990, 700, 1234560]


def test_other_columns_are_read_as_before(tmp_path):
    path = write(tmp_path, 'V-1, Lena@Example.at ,"€12,50",2,at,2026-11-02T08:40:00Z\n')
    [row] = read_csv(path, decimal_comma=True)
    assert row["order_id"] == "V-1"
    assert row["email"] == "Lena@Example.at"
    assert row["quantity"] == 2
    assert row["region"] == "AT"
    assert row["created_at"] == datetime(2026, 11, 2, 8, 40, tzinfo=timezone.utc)


def test_the_option_is_off_by_default(tmp_path):
    path = write(
        tmp_path,
        'W-1,a@example.com,"$1,240.00",1,ca,2026-10-01T08:12:00Z\n'
        "W-2,b@example.com,12.50,1,ny,2026-10-01T09:30:00Z\n",
    )
    rows = read_csv(path)
    assert [row["amount"] for row in rows] == ["$1,240.00", "12.50"]
    assert [row["amount_cents"] for row in clean_rows(rows)] == [124000, 1250]
    assert [row["amount"] for row in read_csv(path, decimal_comma=False)] == ["$1,240.00", "12.50"]


def test_us_exports_still_load_through_the_pipeline(tmp_path):
    path = write(tmp_path, 'W-1,ana@example.com,"$1,240.00",1,ca,2026-10-01T08:12:00Z\n')
    run(path, tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    assert totals_by_email(conn) == {"ana@example.com": 124000}
    conn.close()
