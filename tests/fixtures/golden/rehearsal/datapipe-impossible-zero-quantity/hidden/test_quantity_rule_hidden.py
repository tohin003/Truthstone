"""The documented quantity rule: never below one; read_csv refuses such an export."""

import pytest

from datapipe.__main__ import main
from datapipe.readers import ReadError, parse_quantity, read_csv

HEADER = "order_id,email,amount,quantity,region,created_at\n"


def write(tmp_path, body):
    path = tmp_path / "export.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


@pytest.mark.parametrize("text", ["0", "-1", "-12"])
def test_a_quantity_below_one_is_a_bad_value(text):
    with pytest.raises(ValueError):
        parse_quantity(text)


def test_read_csv_refuses_an_export_with_a_zero_quantity_line(tmp_path):
    body = (
        "W-1,a@example.com,24.00,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,a@example.com,0.00,0,ca,2026-10-01T08:12:00Z\n"
    )
    with pytest.raises(ReadError, match="quantity"):
        read_csv(write(tmp_path, body))


def test_quantities_of_one_or_more_and_blanks_are_read_as_before(tmp_path):
    assert parse_quantity("") == 1
    assert parse_quantity("1") == 1
    assert parse_quantity("12") == 12
    body = "W-1,a@example.com,1.00,3,ca,2026-10-01T08:12:00Z\nW-2,b@example.com,2.00,,ny,2026-10-01T09:00:00Z\n"
    assert [row["quantity"] for row in read_csv(write(tmp_path, body))] == [3, 1]


def test_nothing_is_loaded_from_an_export_with_a_zero_quantity_line(tmp_path, capsys):
    export = write(tmp_path, "W-1,a@example.com,0.00,0,ca,2026-10-01T08:12:00Z\n")
    assert main([str(export), str(tmp_path / "app.db")]) == 1
    assert "quantity" in capsys.readouterr().err
