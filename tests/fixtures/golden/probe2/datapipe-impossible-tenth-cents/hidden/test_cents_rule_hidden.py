"""Hidden: the documented storage rule (whole cents in amount_cents, the schema as it is)."""

import sqlite3

import pytest

from datapipe.db import connect, init_schema
from datapipe.pipeline import run
from datapipe.transforms import TransformError, parse_amount

COLUMNS = [
    ("order_id", "TEXT"),
    ("email", "TEXT"),
    ("amount_cents", "INTEGER"),
    ("quantity", "INTEGER"),
    ("region", "TEXT"),
    ("created_at", "TEXT"),
]


def test_two_decimal_amounts_are_whole_cents():
    for text, cents in [("12.50", 1250), ("$1,240.00", 124000), ("-3", -300), ("0.05", 5)]:
        value = parse_amount(text)
        assert value == cents and type(value) is int


@pytest.mark.parametrize("text", ["12.345", "$1,240.125", "0.001"])
def test_amounts_finer_than_a_cent_are_rejected(text):
    with pytest.raises(TransformError):
        parse_amount(text)


def test_schema_is_unchanged(tmp_path):
    conn = connect(tmp_path / "a.db")
    init_schema(conn)
    columns = [(row["name"], row["type"]) for row in conn.execute("PRAGMA table_info(orders)")]
    tables = sorted(
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not row[0].startswith("sqlite_")
    )
    conn.close()
    assert columns == COLUMNS
    assert tables == ["imports", "orders"]


def test_loaded_amounts_are_stored_as_integers(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,a@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
        'W-2,b@example.com,"$1,240.00",2,ny,2026-10-01T09:30:00Z\n'
        "W-3,c@example.com,-2.05,1,tx,2026-10-02T11:05:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    conn = sqlite3.connect(str(tmp_path / "app.db"))
    rows = conn.execute("SELECT order_id, amount_cents, typeof(amount_cents) FROM orders ORDER BY order_id").fetchall()
    conn.close()
    assert rows == [("W-1", 1250, "integer"), ("W-2", 124000, "integer"), ("W-3", -205, "integer")]
