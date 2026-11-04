"""The nightly job runs end to end, and rotate_logs.sh runs on its own as cron calls it."""

import subprocess
import sys
from pathlib import Path


def environment(tmp_path):
    return {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHON": sys.executable,
        "DATAPIPE_DB": str(tmp_path / "app.db"),
        "NIGHTLY_DATE": "2026-11-03",
    }


def test_the_nightly_job_runs(tmp_path):
    proc = subprocess.run(
        ["./scripts/nightly.sh", "data/orders.csv"],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment(tmp_path),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    extract = Path("var/exports/orders-2026-11-03.csv").read_text(encoding="utf-8").splitlines()
    assert extract[0] == "order_id,email,amount_cents,region,created_at"
    assert len(extract) == 1 + 10
    assert extract[1].startswith("W-2001,ana@example.com,1250,CA,2026-10-01T08:12:00")
    log = Path("var/log/nightly.log").read_text(encoding="utf-8")
    assert "nightly: 2026-11-03: done" in log
    assert "nightly: 2026-11-01: done" in Path("var/log/nightly.log.1").read_text(encoding="utf-8")


def test_rotate_logs_runs_on_its_own(tmp_path):
    api_log = tmp_path / "api.log"
    api_log.write_text("GET /health 200\n", encoding="utf-8")
    proc = subprocess.run(
        ["./scripts/rotate_logs.sh", str(api_log)],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert not api_log.exists()
    assert (tmp_path / "api.log.1").read_text(encoding="utf-8") == "GET /health 200\n"
