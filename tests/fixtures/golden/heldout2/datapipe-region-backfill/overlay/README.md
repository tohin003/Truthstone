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

Amounts are stored as integer cents (`amount_cents`), region codes in upper case (`CA`).

## The database

`data/app.db` is the order history. Each export the shop sends holds the orders placed since
its previous export, and the new file replaces `data/orders.csv`; old exports are not kept.
Every import adds the export's new orders to the database and appends a line to its `imports`
table, so the database holds every order loaded since March 2026, while `data/orders.csv` is
only the latest export. An import never changes an order that is already stored.

A missing database is created by the next import, so a fresh checkout needs no setup.

## Reports

    PYTHONPATH=src python -m datapipe.report data/app.db

prints the revenue per region, one line per region code. The reporting service groups the
same way.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
