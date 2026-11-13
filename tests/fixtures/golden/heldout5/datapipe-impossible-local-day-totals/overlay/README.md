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

## Reporting contract

The reporting service reads `data/app.db` directly and relies on these rules; they change only
together with the service:

- `created_at` is stored as ISO-8601 text in UTC.
- `db.daily_totals` groups orders by their **UTC calendar day** (the first ten characters of
  `created_at`), so a day's total never depends on where the report runs.
- `db.totals_by_email` groups by the normalised (lower-case) email.
