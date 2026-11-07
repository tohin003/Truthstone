from datetime import datetime, timezone

import pytest

from datapipe.readers import ReadError, parse_timestamp, read_csv

HEADER = "order_id,email,amount,quantity,region,created_at\n"


def write(tmp_path, body, header=HEADER):
    path = tmp_path / "export.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_read_csv_converts_columns(tmp_path):
    path = write(tmp_path, " W-1 , Ana@Example.com ,12.50,2,ca,2026-10-01T08:12:00Z\n")
    assert read_csv(path) == [
        {
            "order_id": "W-1",
            "email": "Ana@Example.com",
            "amount": "12.50",
            "quantity": 2,
            "region": "CA",
            "created_at": datetime(2026, 10, 1, 8, 12, tzinfo=timezone.utc),
        }
    ]


def test_blank_quantity_means_one(tmp_path):
    [row] = read_csv(write(tmp_path, "W-1,a@example.com,1.00,,ca,2026-10-01T08:12:00Z\n"))
    assert row["quantity"] == 1


def test_blank_rows_are_skipped(tmp_path):
    body = (
        "W-1,a@example.com,1.00,1,ca,2026-10-01T08:12:00Z\n"
        "\n"
        ",,,,,\n"
        "W-2,b@example.com,2.00,1,ny,2026-10-01T09:00:00Z\n"
    )
    assert [row["order_id"] for row in read_csv(write(tmp_path, body))] == ["W-1", "W-2"]


def test_free_sample_lines_have_quantity_zero(tmp_path):
    # SAMPLES-112: a free sample rides along with an order as a line with quantity 0.
    body = (
        "W-1,a@example.com,24.00,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,a@example.com,0.00,0,ca,2026-10-01T08:12:00Z\n"
    )
    assert [row["quantity"] for row in read_csv(write(tmp_path, body))] == [1, 0]


def test_unknown_columns_are_kept_as_text(tmp_path):
    header = "order_id,email,amount,created_at,channel\n"
    [row] = read_csv(write(tmp_path, "W-1,a@example.com,1.00,2026-10-01T08:12:00Z, web \n", header))
    assert row["channel"] == "web"


def test_missing_required_column(tmp_path):
    with pytest.raises(ReadError, match="created_at"):
        read_csv(write(tmp_path, "W-1,a@example.com,1.00\n", "order_id,email,amount\n"))


def test_bad_value_names_the_line(tmp_path):
    body = (
        "W-1,a@example.com,1.00,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,b@example.com,2.00,zero,ny,2026-10-01T09:00:00Z\n"
    )
    with pytest.raises(ReadError, match="line 3"):
        read_csv(write(tmp_path, body))


def test_parse_timestamp():
    assert parse_timestamp("2026-10-03T09:15:00Z") == datetime(2026, 10, 3, 9, 15, tzinfo=timezone.utc)


def test_parse_timestamp_rejects_garbage():
    with pytest.raises(ValueError):
        parse_timestamp("yesterday")
