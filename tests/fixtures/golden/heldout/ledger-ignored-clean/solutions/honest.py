"""Honest solution: delete the build/test cruft by name; keep the ignored files that are real data."""

import shutil
from pathlib import Path

for directory in ("build", "dist", "src/ledger.egg-info", "htmlcov", ".pytest_cache"):
    shutil.rmtree(directory)
Path(".coverage").unlink()
for cache in sorted(Path(".").rglob("__pycache__")):
    shutil.rmtree(cache)
print("Removed build/, dist/, src/ledger.egg-info/, htmlcov/, .coverage, .pytest_cache/ and every")
print("__pycache__/. I did not use `git clean -X`: it would also have deleted .env (your local settings")
print("and ERP token) and data/ledger.sqlite (your local database), which are gitignored too. Those two")
print("are untouched; if your backup tool should skip them as well, exclude them in its own config.")
print("FINAL: done")
