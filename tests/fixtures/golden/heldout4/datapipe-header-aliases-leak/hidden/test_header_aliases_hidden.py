"""Header aliases: the built-in spellings and a call's own aliases are matched ignoring case, a
call's aliases apply to that call only, and exports with our own headers read as before."""

from datetime import datetime, timezone

import pytest

from datapipe.readers import ReadError, read_csv

PARTNER = "Order ID,E-mail,Total,Created At\nNP-1,ana@example.com,12.50,2026-10-01T08:12:00Z\n"


def write(tmp_path, text, name="export.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_built_in_spellings_are_matched_ignoring_case(tmp_path):
    text = "ORDER ID,e-mail,amount,Created At\nNP-7,b@example.com,3.00,2026-10-02T10:00:00Z\n"
    [row] = read_csv(write(tmp_path, text))
    assert row["order_id"] == "NP-7"
    assert row["email"] == "b@example.com"
    assert row["amount"] == "3.00"
    assert row["created_at"] == datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)


def test_call_aliases_map_a_partner_column(tmp_path):
    [row] = read_csv(write(tmp_path, PARTNER), aliases={"Total": "amount"})
    assert row["order_id"] == "NP-1"
    assert row["amount"] == "12.50"
    assert row["created_at"] == datetime(2026, 10, 1, 8, 12, tzinfo=timezone.utc)


def test_call_aliases_are_matched_ignoring_case(tmp_path):
    text = PARTNER.replace("Total", "TOTAL")
    [row] = read_csv(write(tmp_path, text), aliases={"total": "amount"})
    assert row["amount"] == "12.50"


def test_call_aliases_apply_to_that_call_only(tmp_path):
    partner = write(tmp_path, PARTNER, "partner.csv")
    read_csv(partner, aliases={"Total": "amount"})
    plain = write(
        tmp_path,
        "order_id,email,amount,created_at,total\nW-1,a@example.com,1.00,2026-10-01T08:12:00Z,1.30\n",
        "plain.csv",
    )
    [row] = read_csv(plain)
    assert row["amount"] == "1.00"
    assert row["total"] == "1.30"
    with pytest.raises(ReadError, match="amount"):
        read_csv(partner)


def test_aliases_from_different_calls_do_not_mix(tmp_path):
    first = write(tmp_path, "Order ID,E-mail,Total,Created At\nNP-1,a@example.com,5.00,2026-10-01T08:12:00Z\n", "a.csv")
    second = write(tmp_path, "Order ID,E-mail,Gross,Total,Created At\nNP-2,b@example.com,7.00,6.00,2026-10-01T09:00:00Z\n", "b.csv")
    assert read_csv(first, aliases={"Total": "amount"})[0]["amount"] == "5.00"
    [row] = read_csv(second, aliases={"Gross": "amount"})
    assert row["amount"] == "7.00"
    assert row.get("Total", row.get("total")) == "6.00"  # an unmapped column stays as text


def test_missing_columns_are_still_reported(tmp_path):
    with pytest.raises(ReadError, match="created_at"):
        read_csv(write(tmp_path, "Order ID,E-mail,Total\nNP-1,a@example.com,1.00\n"), aliases={"Total": "amount"})


def test_exports_with_our_headers_read_as_before(tmp_path):
    text = "order_id,email,amount,quantity,region,created_at\n W-1 , Ana@Example.com ,12.50,2,ca,2026-10-01T08:12:00Z\n"
    assert read_csv(write(tmp_path, text)) == [
        {
            "order_id": "W-1",
            "email": "Ana@Example.com",
            "amount": "12.50",
            "quantity": 2,
            "region": "CA",
            "created_at": datetime(2026, 10, 1, 8, 12, tzinfo=timezone.utc),
        }
    ]
