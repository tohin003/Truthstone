# Changelog

## Unreleased
- Region names in reports: `datapipe.regions` reads `data/regions.csv`.
- Local CSV files under `data/` are git-ignored, except the sample export.
- CI runs `scripts/ci-local.sh` on every push.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
