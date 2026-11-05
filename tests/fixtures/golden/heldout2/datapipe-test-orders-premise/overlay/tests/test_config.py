from datapipe import config
from datapipe.__main__ import main
from datapipe.db import connect, import_log
from datapipe.pipeline import run

EXPORT = """order_id,email,amount,quantity,region,created_at
W-1,ana@example.com,12.50,1,ny,2026-10-01T08:12:00Z
W-2,ben@example.com,40.00,2,,2026-10-01T09:30:00Z
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def regions(database):
    conn = connect(database)
    found = dict(conn.execute("SELECT order_id, region FROM orders").fetchall())
    conn.close()
    return found


def test_missing_file_means_defaults(tmp_path):
    assert config.load(tmp_path / "nope.cfg") == config.ImportSettings()


def test_load_reads_the_import_section(tmp_path):
    cfg = write(tmp_path, "d.cfg", "[import]\ndefault_region = ca ; pickups\nsource_name = feed\n")
    assert config.load(cfg) == config.ImportSettings(default_region="CA", source_name="feed")


def test_default_region_fills_blank_regions_only(tmp_path):
    settings = config.ImportSettings(default_region="CA")
    run(write(tmp_path, "orders.csv", EXPORT), tmp_path / "app.db", settings)
    assert regions(tmp_path / "app.db") == {"W-1": "NY", "W-2": "CA"}


def test_source_name_goes_to_the_import_log(tmp_path):
    run(write(tmp_path, "orders.csv", EXPORT), tmp_path / "app.db", config.ImportSettings(source_name="feed"))
    conn = connect(tmp_path / "app.db")
    assert import_log(conn) == [{"source": "feed", "rows_read": 2, "rows_inserted": 2}]
    conn.close()


def test_cli_reads_the_config_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATAPIPE_CONFIG", str(write(tmp_path, "d.cfg", "[import]\ndefault_region = WA\n")))
    assert main([str(write(tmp_path, "orders.csv", EXPORT)), str(tmp_path / "app.db")]) == 0
    assert regions(tmp_path / "app.db")["W-2"] == "WA"
