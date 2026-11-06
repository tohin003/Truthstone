"""Order numbers are case-insensitive: an order never counts twice, whatever case its number is in."""

from datapipe.__main__ import main
from datapipe.db import connect, daily_totals, import_log, order_count, totals_by_email
from datapipe.pipeline import run

HEADER = "order_id,email,amount,quantity,region,created_at\n"

FIRST = (
    "W-501,ana@example.com,12.50,1,ca,2026-10-20T08:00:00Z\n"
    "W-502,ben@example.com,$40.00,2,ny,2026-10-20T09:30:00Z\n"
    "W-503,cara@example.com,-2.50,1,tx,2026-10-20T11:05:00Z\n"
)
# The same three orders with lower-case numbers, plus two late ones.
RESEND = FIRST.replace("W-", "w-") + (
    "w-504,dev@example.com,7.25,1,wa,2026-10-20T22:10:00Z\n"
    "W-505,erin@example.com,100.00,1,or,2026-10-20T23:40:00Z\n"
)


def export(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_a_lower_case_resend_adds_only_the_new_orders(tmp_path):
    database = tmp_path / "app.db"
    run(export(tmp_path, "orders.csv", FIRST), database)
    summary = run(export(tmp_path, "resend.csv", RESEND), database)
    assert summary.rows_read == 5
    assert summary.inserted == 2
    assert summary.already_present == 3
    conn = connect(database)
    assert order_count(conn) == 5
    assert daily_totals(conn) == {"2026-10-20": 1250 + 4000 - 250 + 725 + 10000}
    assert totals_by_email(conn)["ana@example.com"] == 1250
    conn.close()


def test_the_resend_first_and_the_original_second(tmp_path):
    database = tmp_path / "app.db"
    run(export(tmp_path, "resend.csv", RESEND), database)
    again = run(export(tmp_path, "orders.csv", FIRST), database)
    assert (again.inserted, again.already_present) == (0, 3)
    conn = connect(database)
    assert order_count(conn) == 5
    conn.close()


def test_case_variants_inside_one_export_are_one_order(tmp_path):
    body = (
        "W-601,ana@example.com,10.00,1,ca,2026-10-21T08:00:00Z\n"
        "w-601,ana@example.com,10.00,1,ca,2026-10-21T08:00:00Z\n"
        "W-602,ben@example.com,5.00,1,ny,2026-10-21T09:00:00Z\n"
    )
    database = tmp_path / "app.db"
    summary = run(export(tmp_path, "orders.csv", body), database)
    assert summary.inserted == 2
    assert summary.duplicates + summary.already_present == 1
    conn = connect(database)
    assert order_count(conn) == 2
    assert totals_by_email(conn) == {"ana@example.com": 1000, "ben@example.com": 500}
    conn.close()


def test_a_stored_order_is_not_updated_by_a_case_variant(tmp_path):
    database = tmp_path / "app.db"
    run(export(tmp_path, "a.csv", "W-701,ana@example.com,12.50,1,ca,2026-10-21T08:00:00Z\n"), database)
    summary = run(export(tmp_path, "b.csv", "w-701,ana@example.com,99.00,1,ca,2026-10-21T08:00:00Z\n"), database)
    assert summary.inserted == 0
    conn = connect(database)
    assert totals_by_email(conn) == {"ana@example.com": 1250}
    conn.close()


def test_distinct_orders_still_all_load(tmp_path):
    body = (
        "W-801,ana@example.com,1.00,1,ca,2026-10-21T08:00:00Z\n"
        "W-8010,ana@example.com,2.00,1,ca,2026-10-21T08:05:00Z\n"
        "X-801,ana@example.com,4.00,1,ca,2026-10-21T08:10:00Z\n"
        "W-801,ana@example.com,1.00,1,ca,2026-10-21T08:00:00Z\n"
    )
    database = tmp_path / "app.db"
    summary = run(export(tmp_path, "orders.csv", body), database)
    assert (summary.rows_read, summary.inserted) == (4, 3)
    conn = connect(database)
    assert order_count(conn) == 3
    assert import_log(conn) == [{"source": "orders.csv", "rows_read": 4, "rows_inserted": 3}]
    conn.close()


def test_the_command_line_reports_the_resend(tmp_path, capsys):
    database = tmp_path / "app.db"
    assert main([str(export(tmp_path, "orders.csv", FIRST)), str(database)]) == 0
    capsys.readouterr()
    assert main([str(export(tmp_path, "resend.csv", RESEND)), str(database)]) == 0
    assert "2 inserted" in capsys.readouterr().out
