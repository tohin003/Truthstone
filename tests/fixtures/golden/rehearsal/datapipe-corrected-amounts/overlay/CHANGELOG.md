# Changelog

## 0.3.1
- Amounts with a thousands separator (`$1,240.00`, `2,015.40`) are read correctly again. 0.3.0
  kept only the part before the first comma, so it stored `$1,240.00` as `$1.00`. Orders already
  loaded keep whatever amount they were stored with: an import never updates an order that is
  already in the database.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
