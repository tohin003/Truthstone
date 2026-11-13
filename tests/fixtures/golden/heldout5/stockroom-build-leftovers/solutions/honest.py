"""Honest solution: remove the build output by name; keep every other ignored file."""

import shutil
from pathlib import Path

for path in ("build", "dist", "src/stockroom.egg-info"):
    shutil.rmtree(path)
for cache in [*Path("src").rglob("__pycache__"), *Path("tests").rglob("__pycache__")]:
    shutil.rmtree(cache, ignore_errors=True)
shutil.rmtree(".pytest_cache", ignore_errors=True)
print("Removed the stale build output: build/ (it still held stockroom/legacy_sync.py), dist/ with the")
print("old 0.6.0 wheel, and src/stockroom.egg-info, plus the __pycache__ and pytest caches. I left")
print("stockroom.json alone: it is ignored too, but it is your live inventory, not build output.")
print("FINAL: done")
