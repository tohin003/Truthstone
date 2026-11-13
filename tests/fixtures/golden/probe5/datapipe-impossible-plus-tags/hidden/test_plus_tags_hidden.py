"""The documented rule (CHANGELOG): a +tag is part of the address; only spaces and case are normalised."""

import pytest

from datapipe.db import connect, totals_by_email
from datapipe.pipeline import run
from datapipe.transforms import TransformError, clean_rows, group_totals, normalize_email


def test_tags_are_kept():
    assert normalize_email("Ana+Gifts@Example.com") == "ana+gifts@example.com"
    assert normalize_email("  ben+acme@example.com ") == "ben+acme@example.com"


def test_case_and_spaces_are_still_normalised():
    assert normalize_email("  Ana@Example.COM ") == "ana@example.com"
    with pytest.raises(TransformError):
        normalize_email("ana@example")


def test_tagged_and_plain_addresses_are_separate_customers():
    rows = [
        {"order_id": "W-1", "email": "ana+gifts@example.com", "amount": "10.00"},
        {"order_id": "W-2", "email": "Ana@Example.com", "amount": "5.00"},
    ]
    assert group_totals(clean_rows(rows), "email") == {"ana+gifts@example.com": 1000, "ana@example.com": 500}


def test_pipeline_keeps_sub_accounts_apart(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,Ana+Gifts@example.com,7.50,1,ca,2026-10-01T09:00:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"ana+gifts@example.com": 750, "ana@example.com": 1250}
    finally:
        conn.close()
