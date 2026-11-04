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

## The import log

Every run of the pipeline appends one row to the `imports` table (source file, rows read, rows
inserted), including runs that insert nothing: the hourly re-run of an unchanged export logs
`0` inserted. Other systems depend on that:

- The reporting service's freshness check reads the latest entry per source and pages the
  on-call data engineer when a source has had no import logged for 26 hours. A run that leaves
  no entry looks exactly like a pipeline that has stopped.
- The monthly audit report counts pipeline runs from this table.

So a run is always logged; to see only the imports that added orders, filter on
`rows_inserted > 0` when you read the table.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
