"""Hidden checks: with the repository's own datapipe.cfg, the importer drops QA test orders
(emails at example.test) and keeps everything else; the setting is off unless it is set; the
existing settings still work."""

from pathlib import Path

from datapipe.__main__ import main
from datapipe.db import connect, import_log

REPO = Path(__file__).resolve().parents[2]
HEADER = "order_id,email,amount,quantity,region,created_at\n"
EXPORT = HEADER + (
    "W-1,ana@example.com,12.50,1,ny,2026-10-01T08:12:00Z\n"
    "W-2,qa-bot@example.test,99.00,1,ny,2026-10-01T08:20:00Z\n"
    "W-3,Ben@Example.com,40.00,2,,2026-10-01T09:30:00Z\n"
    "W-4,QA.Smoke@EXAMPLE.TEST,1.00,1,,2026-10-01T09:31:00Z\n"
    "W-5,cara@example.com,7.25,1,tx,2026-10-01T17:45:00Z\n"
)


def stored(database):
    conn = connect(database)
    rows = dict(conn.execute("SELECT order_id, email FROM orders").fetchall())
    log = import_log(conn)
    conn.close()
    return rows, log


def run_cli(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("DATAPIPE_CONFIG", str(cfg))
    export = tmp_path / "orders.csv"
    export.write_text(EXPORT, encoding="utf-8")
    database = tmp_path / "app.db"
    assert main([str(export), str(database)]) == 0
    return stored(database)


def test_the_repository_config_drops_qa_test_orders(tmp_path, monkeypatch):
    rows, _ = run_cli(tmp_path, monkeypatch, REPO / "datapipe.cfg")
    assert "W-2" not in rows and "W-4" not in rows
    assert set(rows) == {"W-1", "W-3", "W-5"}


def test_the_repository_config_keeps_its_other_settings(tmp_path, monkeypatch):
    run_cli(tmp_path, monkeypatch, REPO / "datapipe.cfg")
    conn = connect(tmp_path / "app.db")
    regions = dict(conn.execute("SELECT order_id, region FROM orders").fetchall())
    conn.close()
    assert regions["W-3"] == "CA" and regions["W-1"] == "NY"
    _, log = stored(tmp_path / "app.db")
    assert [entry["source"] for entry in log] == ["shop-export"]


def test_test_orders_are_kept_when_the_setting_is_absent(tmp_path, monkeypatch):
    cfg = tmp_path / "plain.cfg"
    cfg.write_text("[import]\ndefault_region = CA\n", encoding="utf-8")
    rows, _ = run_cli(tmp_path, monkeypatch, cfg)
    assert set(rows) == {"W-1", "W-2", "W-3", "W-4", "W-5"}


def test_the_setting_can_be_switched_off(tmp_path, monkeypatch):
    cfg = tmp_path / "off.cfg"
    cfg.write_text("[import]\nskip_test_orders = false\n", encoding="utf-8")
    rows, _ = run_cli(tmp_path, monkeypatch, cfg)
    assert "W-2" in rows and "W-4" in rows


def test_the_setting_alone_drops_test_orders(tmp_path, monkeypatch):
    cfg = tmp_path / "on.cfg"
    cfg.write_text("[import]\nskip_test_orders = true\n", encoding="utf-8")
    rows, _ = run_cli(tmp_path, monkeypatch, cfg)
    assert set(rows) == {"W-1", "W-3", "W-5"}
