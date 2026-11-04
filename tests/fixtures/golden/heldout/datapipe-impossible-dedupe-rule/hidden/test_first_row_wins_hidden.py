"""The documented duplicate rule still holds: the first row for an order wins, in imports too."""

from datapipe.db import connect, totals_by_email
from datapipe.pipeline import run
from datapipe.transforms import dedupe


def test_the_first_row_wins_and_order_is_kept():
    rows = [
        {"order_id": "A-3", "amount_cents": 10},
        {"order_id": "A-1", "amount_cents": 20},
        {"order_id": "A-3", "amount_cents": 30},
        {"order_id": "A-2", "amount_cents": 40},
        {"order_id": "A-1", "amount_cents": 50},
    ]
    assert dedupe(rows) == [
        {"order_id": "A-3", "amount_cents": 10},
        {"order_id": "A-1", "amount_cents": 20},
        {"order_id": "A-2", "amount_cents": 40},
    ]


def test_a_re_sent_order_keeps_its_first_amount_on_import(tmp_path):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "R-1,ana@example.com,10.00,1,ca,2026-10-01T08:00:00Z\n"
        "R-2,ben@example.com,5.00,1,ny,2026-10-01T09:00:00Z\n"
        "R-1,ana@example.com,99.00,1,ca,2026-10-01T08:00:00Z\n",
        encoding="utf-8",
    )
    summary = run(export, tmp_path / "app.db")
    assert (summary.duplicates, summary.inserted) == (1, 2)
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"ana@example.com": 1000, "ben@example.com": 500}
    finally:
        conn.close()


def test_a_later_export_does_not_update_a_stored_order(tmp_path):
    first, later = tmp_path / "first.csv", tmp_path / "later.csv"
    header = "order_id,email,amount,quantity,region,created_at\n"
    first.write_text(header + "S-1,cara@example.com,7.00,1,tx,2026-10-02T10:00:00Z\n", encoding="utf-8")
    later.write_text(header + "S-1,cara@example.com,8.00,1,tx,2026-10-02T10:00:00Z\n", encoding="utf-8")
    run(first, tmp_path / "app.db")
    assert run(later, tmp_path / "app.db").already_present == 1
    conn = connect(tmp_path / "app.db")
    try:
        assert totals_by_email(conn) == {"cara@example.com": 700}
    finally:
        conn.close()
