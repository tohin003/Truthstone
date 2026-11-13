#!/bin/sh
# Run the README's examples (CI's "docs" step). Usage: scripts/check-docs.sh [pytest args]
set -e
cd "$(dirname "$0")/.."
exec python -m pytest -q doctests "$@"
