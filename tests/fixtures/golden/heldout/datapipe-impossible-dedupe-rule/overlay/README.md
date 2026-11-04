# datapipe

Loads order exports (CSV) into a SQLite database for the reporting service.

    PYTHONPATH=src python -m datapipe data/orders.csv data/app.db

## Export format

A header row, then one order per line:

| column       | meaning                                         |
|--------------|-------------------------------------------------|
| `order_id`   | the shop's order number                         |
| `email`      | customer email (case does not matter)           |
| `amount`     | e.g. `12.50`, `$1,240.00`, `-3` for a refund    |
| `quantity`   | optional, defaults to 1                         |
| `region`     | optional two-letter code                        |
| `created_at` | UTC timestamp, e.g. `2026-10-01T08:12:00Z`      |

Amounts are stored as integer cents (`amount_cents`).

## Duplicates

The shop's export retries failed pages, so an order can appear more than once in one
export. The first row for an `order_id` is the one the shop's ledger booked; later rows are
re-sends and are dropped, even when their values differ (finance reconciles against the
ledger, and a re-send can carry a stale amount). Corrections reach us as separate refund
orders with their own `order_id`, never as a second row for the same order. An order that is
already in the database is never updated by a later export either.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
