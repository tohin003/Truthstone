"""Recreate the job host's runtime state under var/ (git-ignored) as the failing night left it.

Runs in the repository after the initial commit. The log shows the last good run and the
first failed one. var/exports/ is empty (finance's sync moved the last extract away) and has
lost its write bit: it is mode 0555, as a restore from a read-only snapshot leaves it. The
committed scripts/rotate_logs.sh lost its executable bit in the same restore (see task.toml's
setup.modes).
"""

from __future__ import annotations

import os
from pathlib import Path

log = Path("var/log")
log.mkdir(parents=True, exist_ok=True)
(log / "nightly.log").write_text(
    "nightly: 2026-11-01: loading data/orders.csv into data/app.db\n"
    "read 12 row(s): 0 inserted, 2 duplicate(s) dropped, 10 already present\n"
    "extract: wrote 10 order(s) to var/exports/orders-2026-11-01.csv\n"
    "nightly: 2026-11-01: done\n",
    encoding="utf-8",
)
exports = Path("var/exports")
exports.mkdir(parents=True, exist_ok=True)
os.chmod(exports, 0o555)
