import pytest

from datapipe.currency import parse_currency
from datapipe.readers import read_csv


def test_currency_codes_are_upper_cased_and_default_to_usd():
    assert parse_currency("eur") == "EUR"
    assert parse_currency("") == "USD"
    with pytest.raises(ValueError):
        parse_currency("euro")


def test_exports_may_carry_a_currency_column(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(
        "order_id,email,amount,created_at,currency\n"
        "W-1,a@example.com,12.50,2026-10-01T08:12:00Z,eur\n"
        "W-2,b@example.com,3.00,2026-10-01T09:00:00Z,\n",
        encoding="utf-8",
    )
    assert [row["currency"] for row in read_csv(path)] == ["EUR", "USD"]
