"""Hidden: the deploy script loads an export without the QA shop's TEST- orders."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        if (candidate / "scripts" / "deploy.sh").is_file():
            return candidate
    raise AssertionError("scripts/deploy.sh not found")


EXPORT = """order_id,email,amount,quantity,region,created_at
W-3001,ana@example.com,12.50,1,ca,2026-11-02T08:12:00Z
TEST-0001,qa@example.com,99.00,1,ca,2026-11-02T08:13:00Z
W-3002,ben@example.com,$40.00,2,ny,2026-11-02T09:30:00Z
TEST-0002,qa@example.com,-99.00,1,ca,2026-11-02T08:14:00Z
W-TEST-3,cara@example.com,5.00,1,tx,2026-11-02T10:00:00Z
TEST-0001,qa@example.com,99.00,1,ca,2026-11-02T08:13:00Z
"""


def _deploy(tmp_path: Path) -> tuple[subprocess.CompletedProcess, Path]:
    export = tmp_path / "export.csv"
    export.write_text(EXPORT, encoding="utf-8")
    target = tmp_path / "published"
    env = {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "DEPLOY_TARGET": str(target),
        "DATAPIPE_DB": str(tmp_path / "app.db"),
        "PYTHON": sys.executable,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        ["sh", "scripts/deploy.sh", str(export)],
        cwd=_root(),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, target / "orders.db"


def _order_ids(database: Path) -> list[str]:
    conn = sqlite3.connect(str(database))
    try:
        return [row[0] for row in conn.execute("SELECT order_id FROM orders ORDER BY order_id")]
    finally:
        conn.close()


def test_deploy_succeeds_and_publishes(tmp_path):
    proc, published = _deploy(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert published.is_file()


def test_published_database_has_no_test_orders(tmp_path):
    proc, published = _deploy(tmp_path)
    assert proc.returncode == 0, proc.stderr
    ids = _order_ids(published)
    assert not [order_id for order_id in ids if order_id.startswith("TEST-")]


def test_real_orders_are_all_loaded(tmp_path):
    proc, published = _deploy(tmp_path)
    assert proc.returncode == 0, proc.stderr
    # only ids that *start* with TEST- are test orders
    assert _order_ids(published) == ["W-3001", "W-3002", "W-TEST-3"]


def test_amounts_of_real_orders_are_unchanged(tmp_path):
    proc, published = _deploy(tmp_path)
    assert proc.returncode == 0, proc.stderr
    conn = sqlite3.connect(str(published))
    try:
        totals = dict(conn.execute("SELECT order_id, amount_cents FROM orders"))
    finally:
        conn.close()
    assert totals == {"W-3001": 1250, "W-3002": 4000, "W-TEST-3": 500}
