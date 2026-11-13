import pytest

from datapipe.db import connect, totals_by_email
from datapipe.pipeline import run
from datapipe.transforms import TransformError, parse_amount


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("19.99", 1999),
        ("0.29", 29),
        ("4.35", 435),
        ("1.15", 115),
        ("9.95", 995),
        ("8.20", 820),
        ("$1.13", 113),
        ("-4.35", -435),
        ("-0.29", -29),
        ("12.50", 1250),
        ("7", 700),
        ("0.5", 50),
        ("1,240.00", 124000),
        ("$12,000", 1200000),
        (" $3.99 ", 399),
    ],
)
def test_parse_amount_is_exact(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("bad", ["", "abc", "12.345", "1.2.3", "$"])
def test_parse_amount_still_rejects_garbage(bad):
    with pytest.raises(TransformError):
        parse_amount(bad)


def test_totals_are_exact_end_to_end(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,created_at\n"
        "W-1,ana@example.com,19.99,2026-10-01T08:00:00Z\n"
        "W-2,ana@example.com,0.29,2026-10-01T09:00:00Z\n"
        "W-3,ben@example.com,4.35,2026-10-02T10:00:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"ana@example.com": 2028, "ben@example.com": 435}
    finally:
        conn.close()
