"""The command line, end to end, run the way scripts/deploy.sh runs it."""

import os
import subprocess
import sys

from datapipe.db import connect, order_count


def run_cli(project_root, *args):
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    return subprocess.run(
        [sys.executable, "-m", "datapipe", *args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_loads_the_sample_export(project_root, tmp_path):
    database = tmp_path / "app.db"
    proc = run_cli(project_root, "data/orders.csv", str(database))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "read 12 row(s): 10 inserted, 2 duplicate(s) dropped, 0 already present"
    conn = connect(database)
    try:
        assert order_count(conn) == 10
    finally:
        conn.close()


def test_cli_reports_a_broken_export(project_root, tmp_path):
    broken = tmp_path / "broken.csv"
    broken.write_text("order_id,email\nW-1,a@example.com\n", encoding="utf-8")
    proc = run_cli(project_root, str(broken), str(tmp_path / "app.db"))
    assert proc.returncode == 1
    assert "missing column" in proc.stderr
