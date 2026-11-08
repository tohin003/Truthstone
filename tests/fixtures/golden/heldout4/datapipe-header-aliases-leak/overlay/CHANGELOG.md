# Changelog

## Unreleased
- Partner header spellings: `readers.HEADER_ALIASES` and `read_csv(path, aliases=...)`.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
