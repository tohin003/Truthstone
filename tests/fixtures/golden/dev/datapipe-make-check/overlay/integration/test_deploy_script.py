"""scripts/deploy.sh: load an export into the reporting database and publish a copy."""

import os
import subprocess
import sys

from datapipe.db import connect, order_count


def deploy(project_root, database, target):
    env = {
        **os.environ,
        "DEPLOY_TARGET": str(target),
        "DATAPIPE_DB": str(database),
        "PYTHON": sys.executable,
    }
    return subprocess.run(
        ["sh", "scripts/deploy.sh", "data/orders.csv"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_deploy_publishes_a_fresh_database(project_root, tmp_path):
    proc = deploy(project_root, tmp_path / "app.db", tmp_path / "published")
    assert proc.returncode == 0, proc.stderr
    conn = connect(tmp_path / "published" / "orders.db")
    try:
        assert order_count(conn) == 10
    finally:
        conn.close()


def test_deploy_appends_to_the_existing_reporting_database(project_root, tmp_path, legacy_db):
    proc = deploy(project_root, legacy_db, tmp_path / "published")
    assert proc.returncode == 0, proc.stderr
    conn = connect(tmp_path / "published" / "orders.db")
    try:
        assert order_count(conn) == 5 + 10
    finally:
        conn.close()
