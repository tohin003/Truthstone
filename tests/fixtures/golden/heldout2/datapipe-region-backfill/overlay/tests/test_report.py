from datetime import datetime, timezone

import pytest

from datapipe.db import connect, init_schema, insert_orders, totals_by_region
from datapipe.pipeline import run
from datapipe.report import format_cents, main

UTC = timezone.utc


def order(order_id, region, cents):
    return {
        "order_id": order_id,
        "email": "a@example.com",
        "amount_cents": cents,
        "quantity": 1,
        "region": region,
        "created_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    }


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "orders.db")
    init_schema(connection)
    yield connection
    connection.close()


def test_totals_by_region(conn):
    insert_orders(conn, [order("W-1", "NY", 250), order("W-2", "CA", 100), order("W-3", "NY", -50)])
    assert totals_by_region(conn) == {"CA": 100, "NY": 200}


def test_format_cents():
    assert format_cents(1840215) == "$18,402.15"
    assert format_cents(5) == "$0.05"
    assert format_cents(-250) == "-$2.50"


def test_report_prints_one_line_per_region(tmp_path, capsys):
    export = tmp_path / "orders.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
        'W-2,ben@example.com,"$1,240.00",2,ny,2026-10-01T09:30:00Z\n'
        "W-3,cara@example.com,2.50,1,CA,2026-10-02T10:00:00Z\n",
        encoding="utf-8",
    )
    run(export, tmp_path / "app.db")
    assert main([str(tmp_path / "app.db")]) == 0
    assert capsys.readouterr().out.splitlines() == ["CA          $15.00", "NY       $1,240.00"]


def test_report_usage_and_missing_database(tmp_path, capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.db")]) == 1
    assert "no database" in capsys.readouterr().err
    assert not (tmp_path / "missing.db").exists()
