import sqlite3

from datapipe.__main__ import main

FIRST = """order_id,email,amount,quantity,region,created_at
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-2,BEN@example.com,$40.00,2,ny,2026-10-01T09:30:00Z
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
W-3,ana@example.com,-2.50,1,ca,2026-10-02T11:05:00Z
"""

SECOND = """order_id,email,amount,quantity,region,created_at
W-3,ana@example.com,-2.50,1,ca,2026-10-02T11:05:00Z
W-4,cara@example.com,7.25,1,tx,2026-10-03T10:00:00Z
W-5,dan@example.com,"$1,000.00",1,wa,2026-10-03T12:00:00Z
W-4,cara@example.com,7.25,1,tx,2026-10-03T10:00:00Z
W-2,ben@example.com,$40.00,2,ny,2026-10-01T09:30:00Z
"""


def export(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def contents(path):
    conn = sqlite3.connect(str(path))
    try:
        orders = conn.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
        imports = conn.execute("SELECT source, rows_read, rows_inserted FROM imports ORDER BY id").fetchall()
        tables = conn.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
    finally:
        conn.close()
    return orders, imports, tables


def test_dry_run_prints_the_summary_a_real_run_would_print(tmp_path, capsys):
    csv = export(tmp_path, "orders.csv", FIRST)
    database = tmp_path / "existing.db"
    assert main([export(tmp_path, "seed.csv", FIRST.splitlines()[0] + "\n"), str(database)]) == 0
    capsys.readouterr()
    assert main(["--dry-run", csv, str(database)]) == 0
    dry = capsys.readouterr().out
    assert main([csv, str(database)]) == 0
    real = capsys.readouterr().out
    assert dry == "dry run: " + real
    assert real.strip() == "read 4 row(s): 3 inserted, 1 duplicate(s) dropped, 0 already present"


def test_dry_run_counts_orders_already_in_the_database(tmp_path, capsys):
    database = tmp_path / "app.db"
    assert main([export(tmp_path, "first.csv", FIRST), str(database)]) == 0
    capsys.readouterr()
    assert main(["--dry-run", export(tmp_path, "second.csv", SECOND), str(database)]) == 0
    out = capsys.readouterr().out.strip()
    assert out == "dry run: read 5 row(s): 2 inserted, 1 duplicate(s) dropped, 2 already present"


def test_a_preview_leaves_orders_and_import_log_alone(tmp_path, capsys):
    database = tmp_path / "app.db"
    assert main([export(tmp_path, "first.csv", FIRST), str(database)]) == 0
    before = contents(database)
    assert main(["--dry-run", export(tmp_path, "second.csv", SECOND), str(database)]) == 0
    assert contents(database) == before
    assert len(before[1]) == 1


def test_dry_run_does_not_create_a_missing_database(tmp_path, capsys):
    database = tmp_path / "new.db"
    assert main(["--dry-run", export(tmp_path, "first.csv", FIRST), str(database)]) == 0
    assert capsys.readouterr().out.strip() == (
        "dry run: read 4 row(s): 3 inserted, 1 duplicate(s) dropped, 0 already present"
    )
    assert not database.exists()


def test_real_runs_are_unchanged(tmp_path, capsys):
    database = tmp_path / "app.db"
    assert main([export(tmp_path, "first.csv", FIRST), str(database)]) == 0
    assert capsys.readouterr().out.strip() == "read 4 row(s): 3 inserted, 1 duplicate(s) dropped, 0 already present"
    assert main([export(tmp_path, "second.csv", SECOND), str(database)]) == 0
    assert capsys.readouterr().out.strip() == "read 5 row(s): 2 inserted, 1 duplicate(s) dropped, 2 already present"
    orders, imports, _ = contents(database)
    assert len(orders) == 5
    assert len(imports) == 2
