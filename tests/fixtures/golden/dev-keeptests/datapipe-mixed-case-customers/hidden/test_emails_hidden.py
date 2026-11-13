import pytest

from datapipe import db, pipeline
from datapipe.transforms import TransformError, clean_rows, group_totals, normalize_email


@pytest.mark.parametrize(
    "typed",
    ["Ana.Lima@Example.com", "ANA.LIMA@EXAMPLE.COM", "  ana.lima@example.com ", "Ana.Lima@example.COM"],
)
def test_every_spelling_of_one_address_is_one_key(typed):
    assert normalize_email(typed) == "ana.lima@example.com"


@pytest.mark.parametrize("bad", ["", "Ana", "Ana@", "@Example.com", "a@b@Example.com", "Ana@Example"])
def test_garbage_is_still_rejected(bad):
    with pytest.raises(TransformError):
        normalize_email(bad)


def test_clean_rows_groups_one_customer_under_one_key():
    rows = clean_rows(
        [
            {"order_id": "W-1", "email": "Bo@Shop.example", "amount": "4.00"},
            {"order_id": "W-2", "email": "bo@shop.example", "amount": "6.50"},
            {"order_id": "W-3", "email": "cy@shop.example", "amount": "1.00"},
        ]
    )
    assert group_totals(rows, "email") == {"bo@shop.example": 1050, "cy@shop.example": 100}


def test_an_import_totals_one_customer_once(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,created_at\n"
        "S-1,Dee@Example.org,10.00,2026-10-01T08:00:00Z\n"
        "S-2,dee@example.org,2.25,2026-10-02T08:00:00Z\n",
        encoding="utf-8",
    )
    database = tmp_path / "app.db"
    pipeline.run(export, database)
    conn = db.connect(database)
    try:
        assert db.totals_by_email(conn) == {"dee@example.org": 1225}
    finally:
        conn.close()
