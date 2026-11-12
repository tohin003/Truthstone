import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

EXPORT = """order_id,email,amount,quantity,region,created_at
W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z
T-7,qa-bot@example.com,1.00,1,ca,2026-10-01T08:20:00Z
W-2,ben@example.com,40.00,2,ny,2026-10-01T09:30:00Z
QA-3,qa-bot@example.com,5.00,1,ny,2026-10-01T09:45:00Z
T-8,qa-bot@example.com,999.99,5,ny,2026-10-02T10:00:00Z
W-3,cara@example.com,7.25,1,tx,2026-10-02T11:05:00Z
"""


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k != "DATAPIPE_SKIP_PREFIXES"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")])
    env.update(extra)
    return env


def stored_ids(database):
    conn = sqlite3.connect(str(database))
    try:
        return sorted(row[0] for row in conn.execute("SELECT order_id FROM orders"))
    finally:
        conn.close()


def write_export(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text(EXPORT, encoding="utf-8")
    return path


def load(tmp_path, env):
    database = tmp_path / "app.db"
    proc = subprocess.run(
        [sys.executable, "-m", "datapipe", str(write_export(tmp_path)), str(database)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return stored_ids(database)


def test_listed_prefixes_are_skipped(tmp_path):
    ids = load(tmp_path, clean_env(DATAPIPE_SKIP_PREFIXES="T-,QA-"))
    assert ids == ["W-1", "W-2", "W-3"]


def test_a_single_prefix(tmp_path):
    ids = load(tmp_path, clean_env(DATAPIPE_SKIP_PREFIXES="T-"))
    assert ids == ["QA-3", "W-1", "W-2", "W-3"]


def test_without_the_setting_every_order_loads(tmp_path):
    ids = load(tmp_path, clean_env())
    assert ids == ["QA-3", "T-7", "T-8", "W-1", "W-2", "W-3"]


def test_the_deploy_script_skips_staging_orders(tmp_path):
    target = tmp_path / "published"
    database = tmp_path / "deploy.db"
    proc = subprocess.run(
        ["sh", "scripts/deploy.sh", str(write_export(tmp_path))],
        cwd=ROOT,
        env=clean_env(DEPLOY_TARGET=str(target), DATAPIPE_DB=str(database), PYTHON=sys.executable),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    ids = stored_ids(target / "orders.db")
    assert "T-7" not in ids and "T-8" not in ids
    assert {"W-1", "W-2", "W-3"} <= set(ids)
