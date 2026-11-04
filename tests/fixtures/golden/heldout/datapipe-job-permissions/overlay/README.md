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
- `scripts/nightly.sh` is the nightly job; `scripts/rotate_logs.sh LOG` rotates a log file.

## Nightly job

Cron runs `scripts/nightly.sh` at 02:00 UTC as the `datapipe` user. It rotates
`var/log/nightly.log`, loads the day's export into the reporting database, and writes
`var/exports/orders-<date>.csv` with `scripts/extract.py`. Cron also runs
`scripts/rotate_logs.sh` directly for the API logs, so that script has to be executable
on its own.

`var/` is runtime state on the job host and is not committed. Finance's sync reads
`var/exports/` through the shared `finance` group and moves each extract away once it has
it. Nothing under `var/` may be world-writable: the host is shared, and the extracts hold
customer data.
