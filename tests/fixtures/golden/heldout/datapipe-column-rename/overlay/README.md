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

## Schema

| table     | columns                                                                  |
|-----------|--------------------------------------------------------------------------|
| `orders`  | `order_id` (key), `email`, `amount_cents`, `quantity`, `region`, `created_at` |
| `imports` | `id`, `source`, `rows_read`, `rows_inserted`                              |

The reporting database is rebuilt from the exports after every deploy, so a schema change
needs no migration.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
- `scripts/top_customers.sh [DATABASE] [N]` lists the N customers who spent the most.

## Reports

    PYTHONPATH=src python -m datapipe report data/app.db

prints revenue per region; the query is `scripts/report.sql`.
