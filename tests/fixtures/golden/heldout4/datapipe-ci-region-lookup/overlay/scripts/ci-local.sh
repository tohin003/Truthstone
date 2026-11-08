#!/bin/sh
# Run the checks exactly as CI does (.github/workflows/ci.yml runs this script on a fresh clone).
#
#   PYTHON  interpreter to use (default: python3)
set -eu
cd "$(dirname "$0")/.."

# CI starts from a fresh clone: no untracked or ignored files. Remove ours so the run matches.
git clean -xdfq

"${PYTHON:-python3}" -m pytest -q
