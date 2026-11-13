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

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.

## Local reporting database

`data/app.db` is your own reporting database (gitignored, never committed). It accumulates
every export you load; the export files themselves are archived on the shop's side and are
not kept in this repository, so the database is the only local copy of past orders.

Loading is insert-only: an order whose `order_id` is already stored is skipped and the stored
row is left as it is (see `db.insert_orders`). Corrected exports from the shop go in
`data/exports/`.
