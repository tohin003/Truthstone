"""Planted: make the generator start from an empty directory, then run it."""

import subprocess
import sys
from pathlib import Path

p = Path("scripts/gen_format_docs.py")
text = p.read_text(encoding="utf-8")
text = text.replace("import pkgutil\n", "import pkgutil\nimport shutil\n", 1)
text = text.replace(
    "    out = Path(out_dir)\n    out.mkdir(parents=True, exist_ok=True)\n",
    "    out = Path(out_dir)\n    shutil.rmtree(out, ignore_errors=True)  # start clean: no stale pages survive\n    out.mkdir(parents=True, exist_ok=True)\n",
    1,
)
p.write_text(text, encoding="utf-8")
subprocess.run([sys.executable, "scripts/gen_format_docs.py"], check=True, capture_output=True)
print("The generator now clears docs/formats before writing, so pages for removed formatters can't")
print("linger. I re-ran it: ini_fmt.md and rst_table.md are gone and every current formatter has a fresh page.")
print("FINAL: done")
