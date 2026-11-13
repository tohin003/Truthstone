# Changelog

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.2
- Emails are trimmed and lower-cased on import, so one customer always groups under one key.
  Orders imported earlier keep the email exactly as the export spelled it.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
