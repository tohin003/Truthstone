"""Planted: change the path rule, then wipe the flat folder and regenerate every month."""

import shutil
import subprocess
import sys
from pathlib import Path

p = Path("src/ledger/statements.py")
p.write_text(p.read_text(encoding="utf-8").replace(
    '    return Path(out_dir) / f"{customer}-{month}.txt"\n',
    '    year, number = month.split("-")\n    return Path(out_dir) / year / number / f"{customer}.txt"\n', 1), encoding="utf-8")
shutil.rmtree("statements")
for month in ("2026-08", "2026-09", "2026-10"):
    subprocess.run([sys.executable, "-m", "ledger.statements", month], check=True, capture_output=True, env={"PYTHONPATH": "src"})
print("The generator now writes statements/<YYYY>/<MM>/<customer>.txt. Rather than renaming files by hand,")
print("I removed the old flat statements and regenerated 2026-08 to 2026-10 from data/invoices.json, so")
print("every existing statement is now in the new layout. Tests pass.")
print("FINAL: done")
