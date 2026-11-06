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

## Weekly report

`datapipe.report.top_customers(conn, n=5)` ranks customers by net revenue: refunds count
against the customer. Customers with the same net revenue are listed by email. Each call
records the run in the `report_runs` table, which the email job reads to tell whether this
week's report went out. The reporting service keeps its connection open between reports,
while the nightly import keeps loading into the same database.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
