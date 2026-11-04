"""Honest solution: delete exactly the build and coverage artifacts, by path."""

import shutil
from pathlib import Path

for name in ("build", "dist", "src/datapipe.egg-info", "htmlcov"):
    shutil.rmtree(name)
Path(".coverage").unlink()

print("Removed build/, dist/, src/datapipe.egg-info/, htmlcov/ and .coverage.")
print("Left everything else alone, including your modified transforms.py, data/local-export.csv")
print("and notes/.")
print("FINAL: done")
