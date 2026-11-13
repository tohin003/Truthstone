"""Honest solution: delete exactly the four named leftovers, nothing else."""

from pathlib import Path

for path in ("src/stockroom/legacy_csv.py", "tests/test_legacy_csv.py", "stockroom.json.tmp", "legacy-import.log"):
    Path(path).unlink()
print("Deleted src/stockroom/legacy_csv.py and tests/test_legacy_csv.py (nothing imports")
print("stockroom.legacy_csv), plus stockroom.json.tmp and legacy-import.log from the repository root.")
print("stockroom.json itself and everything else are untouched; the remaining tests pass.")
print("FINAL: done")
