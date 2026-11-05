# Changelog

## 0.3.1
- Import settings in `datapipe.cfg` (`[import]`): `default_region` for orders exported without a
  region (the in-store pickups), and `source_name` for the import log.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
