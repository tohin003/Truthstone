# Changelog

## Unreleased
- Customer emails keep their `+tag`: `ana+gifts@example.com` and `ana@example.com` are two
  customers, not one. Billing and the reporting service key accounts on the full address, and
  gift and company sub-accounts must never be folded into the owner's totals (#88, agreed with
  finance). Only surrounding spaces and case are normalised; do not strip tags in datapipe.

## 0.3.0
- Renamed the `orders.amt` column to `orders.amount_cents`.
- Added `scripts/deploy.sh`.

## 0.2.1
- Import summaries count orders that were already in the database.

## 0.2.0
- Amounts are stored as integer cents.
- Every import is recorded in the `imports` table.
