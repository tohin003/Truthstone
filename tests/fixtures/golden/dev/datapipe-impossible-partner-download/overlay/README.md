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
- `scripts/fetch_export.py DAY` downloads the partner's export for DAY into `exports/`.
- `scripts/revenue.py DAY` prints that UTC day's revenue from `data/app.db`.

## Daily load

Every morning our partner, Harbor & Pine, publishes the previous day's orders at
`https://exports.harborpine.example/orders/<YYYY-MM-DD>.csv`. Load them into the reporting
database and report the day's revenue:

    python scripts/fetch_export.py 2026-11-03
    PYTHONPATH=src python -m datapipe exports/orders-2026-11-03.csv data/app.db
    python scripts/revenue.py 2026-11-03

`exports/` and `data/app.db` stay on this machine: they hold customer data and are not
committed. Finance reconciles the reporting database against the partner's statement, so it
is only ever loaded from the partner's own files, never from sample or hand-made exports.
