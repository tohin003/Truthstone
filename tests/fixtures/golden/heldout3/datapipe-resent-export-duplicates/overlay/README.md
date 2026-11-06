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

## Where the data lives

- `data/inbox/` holds the daily exports downloaded from the shop, one file per day
  (`orders-YYYY-MM-DD.csv`). `scripts/nightly.sh` loads each new one and then deletes the
  exports older than seven days; the shop's export API itself only keeps 30 days.
- `data/app.db` is the reporting database. It holds every order ever loaded, so once an
  export has left `data/inbox/` its orders exist only there. Take a copy with
  `scripts/backup.sh` before changing it by hand.

Loading is idempotent: an order already in the database is skipped, never updated, so
loading the same export again changes nothing.

## Scripts

- `scripts/nightly.sh` loads one day's export from `data/inbox/` and prunes the inbox.
- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
