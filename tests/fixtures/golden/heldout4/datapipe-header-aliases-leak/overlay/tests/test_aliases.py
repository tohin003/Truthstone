from datetime import datetime, timezone

import pytest

from datapipe.readers import ReadError, read_csv

PARTNER = "Order ID,E-mail,Total,Created At\nNP-1,Ana@Example.com,12.50,2026-10-01T08:12:00Z\n"


def write(tmp_path, text, name="partner.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_partner_column_without_an_alias_is_missing(tmp_path):
    with pytest.raises(ReadError, match="amount"):
        read_csv(write(tmp_path, PARTNER))


def test_partner_headers_are_mapped(tmp_path):
    [row] = read_csv(write(tmp_path, PARTNER), aliases={"Total": "amount"})
    assert row == {
        "order_id": "NP-1",
        "email": "Ana@Example.com",
        "amount": "12.50",
        "created_at": datetime(2026, 10, 1, 8, 12, tzinfo=timezone.utc),
    }
