#!/bin/sh
# Nightly rollout report for the on-call dashboard: how the storefront's rollout flags decide
# for a sample user. CI captures stdout into the dashboard's log viewer, which renders ANSI colours.
# Run from anywhere: sh scripts/rollout-report.sh
set -eu
cd "$(dirname "$0")/.."

for flag in new-checkout search-v2; do
  node src/cli.ts explain flags/storefront.json "$flag" --user user-1 --country DE
done
