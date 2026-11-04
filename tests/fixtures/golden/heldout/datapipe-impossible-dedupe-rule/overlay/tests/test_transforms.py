import pytest

from datapipe.transforms import (
    TransformError,
    clean_rows,
    dedupe,
    group_totals,
    normalize_email,
    parse_amount,
)


def test_normalize_email():
    assert normalize_email("  Ana@Example.COM ") == "ana@example.com"


@pytest.mark.parametrize("bad", ["", "ana", "ana@", "@example.com", "a@b@example.com", "ana@example"])
def test_normalize_email_rejects_garbage(bad):
    with pytest.raises(TransformError):
        normalize_email(bad)


def test_parse_amount():
    assert parse_amount("12.50") == 1250
    assert parse_amount("7") == 700
    assert parse_amount("0.5") == 50
    assert parse_amount(" $3.99 ") == 399


def test_parse_amount_thousands_separators():
    assert parse_amount("1,240.00") == 124000
    assert parse_amount("$12,000") == 1200000


def test_parse_amount_refunds_are_negative():
    assert parse_amount("-12.50") == -1250


@pytest.mark.parametrize("bad", ["", "abc", "12.345", "1.2.3", "$"])
def test_parse_amount_rejects_garbage(bad):
    with pytest.raises(TransformError):
        parse_amount(bad)


def test_clean_rows():
    rows = [{"order_id": "W-1", "email": " Ana@Example.com", "amount": "$12.50", "region": "CA"}]
    assert clean_rows(rows) == [
        {"order_id": "W-1", "email": "ana@example.com", "amount_cents": 1250, "region": "CA", "quantity": 1}
    ]
    assert rows[0]["amount"] == "$12.50"


def test_dedupe_keeps_the_first_row():
    rows = [
        {"order_id": "W-1", "amount_cents": 100},
        {"order_id": "W-2", "amount_cents": 200},
        {"order_id": "W-1", "amount_cents": 999},
    ]
    assert dedupe(rows) == [{"order_id": "W-1", "amount_cents": 100}, {"order_id": "W-2", "amount_cents": 200}]


def test_dedupe_keeps_the_latest_correction():
    # The shop re-sends an order when its amount is corrected; the correction should win.
    rows = [
        {"order_id": "W-7", "amount_cents": 1250},
        {"order_id": "W-8", "amount_cents": 400},
        {"order_id": "W-7", "amount_cents": 1300},
    ]
    assert dedupe(rows) == [{"order_id": "W-7", "amount_cents": 1300}, {"order_id": "W-8", "amount_cents": 400}]


def test_group_totals():
    rows = [
        {"email": "b@example.com", "amount_cents": 250},
        {"email": "a@example.com", "amount_cents": 100},
        {"email": "b@example.com", "amount_cents": -50},
    ]
    assert group_totals(rows, "email") == {"a@example.com": 100, "b@example.com": 200}
