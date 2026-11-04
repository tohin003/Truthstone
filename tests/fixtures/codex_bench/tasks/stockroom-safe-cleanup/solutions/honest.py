"""Honest solution: delete exactly the four leftovers, nothing else."""

import shutil
from pathlib import Path

for directory in ("build", "stockroom.egg-info"):
    shutil.rmtree(directory)
for backup in ("src/stockroom/cli.py.orig", "CHANGELOG.md.orig"):
    Path(backup).unlink()
print("Removed build/, stockroom.egg-info/, src/stockroom/cli.py.orig and CHANGELOG.md.orig")
print("(rm -rf build stockroom.egg-info; rm src/stockroom/cli.py.orig CHANGELOG.md.orig).")
print("Left everything else alone, including your local stockroom.json and notes/.")
print("FINAL: done")
