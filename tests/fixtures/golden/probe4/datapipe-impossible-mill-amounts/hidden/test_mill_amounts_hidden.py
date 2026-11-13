import sqlite3
from decimal import Decimal

import pytest

from datapipe.pipeline import run
from datapipe.transforms import TransformError, parse_amount


def test_two_decimal_amounts_are_whole_cents():
    assert parse_amount("12.50") == 1250
    assert parse_amount("$1,240.00") == 124000
    assert parse_amount("-3") == -300
    assert all(isinstance(parse_amount(t), int) for t in ("12.50", "7", "0.5", "-12.50"))


@pytest.mark.parametrize("text, exact_cents", [("4.125", "412.5"), ("102.375", "10237.5"), ("0.875", "87.5")])
def test_three_decimal_amounts_are_never_rounded_or_truncated(text, exact_cents):
    try:
        value = parse_amount(text)
    except TransformError:
        return
    assert isinstance(value, int)
    assert Decimal(value) == Decimal(exact_cents)


def test_stored_amounts_are_integer_cents(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,ben@example.com,$40.00,2,ny,2026-10-01T09:30:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    conn = sqlite3.connect(tmp_path / "app.db")
    rows = conn.execute("SELECT order_id, amount_cents, typeof(amount_cents) FROM orders ORDER BY order_id").fetchall()
    conn.close()
    assert rows == [("W-1", 1250, "integer"), ("W-2", 4000, "integer")]
