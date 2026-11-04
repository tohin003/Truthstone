# Changelog

## 0.4.0 (unreleased)
- Local settings in `datapipe.toml`, grouped into sections (`[database]`, `[deploy]`, `[partner]`,
  `[report]`) with `version = 2`; `python -m datapipe EXPORT.csv` loads into `[database] path`.
  A datapipe.toml in the flat 0.3 layout is refused with a message: move your values into the
  new layout (see `datapipe.example.toml`).

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
