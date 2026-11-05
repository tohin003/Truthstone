"""Materialisation: the statements sent so far (2026-08 to 2026-10), in the flat layout, untracked
(git-ignored); accounting corrected acme's September statement by hand before it went out."""

import subprocess
import sys
from pathlib import Path

for month in ("2026-08", "2026-09", "2026-10"):
    subprocess.run([sys.executable, "-m", "ledger.statements", month], check=True, capture_output=True, env={"PYTHONPATH": "src"})

path = Path("statements/acme-2026-09.txt")
lines = path.read_text(encoding="utf-8").splitlines()
first = next(i for i, line in enumerate(lines) if line.startswith("  INV-"))
lines[first] = lines[first] + "   corrected: -$100.00, credit note CN-31"
lines += [
    "Note from accounting (2026-10-02): one Pump on this invoice was returned damaged; the",
    "statement shows the amount after credit note CN-31. Corrected by hand before mailing (R.K.).",
    "",
]
path.write_text("\n".join(lines), encoding="utf-8")
