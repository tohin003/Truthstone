#!/bin/sh
# Run the consumers' tests (consumers/) against this checkout of fetchkit.
# CI runs this as its own job; plain `pytest` only runs tests/.
#
#   PYTHON  interpreter to use (default: python3)
set -eu
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m pytest -q consumers "$@"
