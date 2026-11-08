#!/bin/sh
# What CI runs, in this order: the unit tests (tests/), then the replay suite (replay/).
# Run it before you push. PYTHON picks the interpreter (default: python, else python3).
set -eu
cd "$(dirname "$0")/.."
python="${PYTHON:-python}"
command -v "$python" >/dev/null 2>&1 || python=python3
echo "== unit tests"
"$python" -m pytest -q tests
echo "== replay suite"
"$python" -m pytest -q replay
