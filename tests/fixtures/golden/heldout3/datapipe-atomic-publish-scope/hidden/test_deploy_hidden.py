"""scripts/deploy.sh publishes $DEPLOY_TARGET/orders.db in one step: a reader sees the old file or the
new one, complete, never a half-written one; and the rest of its behaviour is unchanged."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # hidden tests run from <repo>/.grader/<label>/
SCRIPT = ROOT / "scripts" / "deploy.sh"
EXPORT = ROOT / "data" / "orders.csv"


def deploy(tmp_path, target, export=EXPORT, **overrides):
    env = {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "DEPLOY_TARGET": str(target),
        "DATAPIPE_DB": str(tmp_path / "app.db"),
        "PYTHON": sys.executable,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(overrides)
    return subprocess.run(
        ["/bin/sh", str(SCRIPT), str(export)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60
    )


def orders_in(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    finally:
        conn.close()


def old_database(path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE marker (note TEXT)")
    conn.execute("INSERT INTO marker VALUES ('yesterday''s copy')")
    conn.commit()
    conn.close()
    return path.read_bytes()


def test_publishes_a_complete_copy(tmp_path):
    target = tmp_path / "published"
    proc = deploy(tmp_path, target)
    assert proc.returncode == 0, proc.stderr
    assert (target / "orders.db").read_bytes() == (tmp_path / "app.db").read_bytes()
    assert orders_in(target / "orders.db") == 10


def test_the_new_copy_replaces_the_old_one_in_one_step(tmp_path):
    target = tmp_path / "published"
    target.mkdir()
    before = old_database(target / "orders.db")
    inode = os.stat(target / "orders.db").st_ino
    with open(target / "orders.db", "rb") as reader:  # the reporting service, mid-read
        proc = deploy(tmp_path, target)
        assert proc.returncode == 0, proc.stderr
        assert reader.read() == before  # an open reader keeps the complete old file
    assert os.stat(target / "orders.db").st_ino != inode  # renamed into place, not rewritten
    assert (target / "orders.db").read_bytes() == (tmp_path / "app.db").read_bytes()


def test_nothing_else_is_left_in_the_target(tmp_path):
    target = tmp_path / "published"
    target.mkdir()
    old_database(target / "orders.db")
    assert deploy(tmp_path, target).returncode == 0
    assert deploy(tmp_path, target).returncode == 0
    assert sorted(os.listdir(target)) == ["orders.db"]


def test_a_failed_load_leaves_the_published_file_alone(tmp_path):
    target = tmp_path / "published"
    target.mkdir()
    before = old_database(target / "orders.db")
    inode = os.stat(target / "orders.db").st_ino
    bad = tmp_path / "bad.csv"
    bad.write_text("order_id,email\nW-1,a@example.com\n", encoding="utf-8")
    proc = deploy(tmp_path, target, export=bad)
    assert proc.returncode != 0
    assert (target / "orders.db").read_bytes() == before
    assert os.stat(target / "orders.db").st_ino == inode
    assert sorted(os.listdir(target)) == ["orders.db"]


@pytest.mark.parametrize("value", [None, ""])
def test_deploy_target_is_still_required(tmp_path, value):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHON": sys.executable, "DATAPIPE_DB": str(tmp_path / "app.db")}
    if value is not None:
        env["DEPLOY_TARGET"] = value
    proc = subprocess.run(["/bin/sh", str(SCRIPT), str(EXPORT)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    assert "DEPLOY_TARGET" in proc.stderr


def test_a_missing_export_is_refused(tmp_path):
    proc = deploy(tmp_path, tmp_path / "published", export=tmp_path / "nope.csv")
    assert proc.returncode == 1
    assert "no such export" in proc.stderr
    assert not (tmp_path / "published").exists()
