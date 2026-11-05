# Changelog

## Unreleased
- `python -m datapipe.report DATABASE.db` prints the revenue per region.

## 0.3.1
- Region codes are stored in upper case (`ca` -> `CA`), as the reporting service expects.
  Orders imported before 0.3.1 keep the case the shop exported them in.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
