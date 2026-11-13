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

## Backups

`scripts/backup.sh` copies `data/app.db` into `backups/` (gitignored: local only) as
`app-<UTC timestamp>.db`. It refuses to run once `backups/` holds 30 copies, so the folder never
silently fills the disk; prune it by hand, following the retention rule:

- keep the **7 most recent** copies;
- keep the **first copy of every calendar month**, forever. These monthly copies are the only
  record of the month-end figures, and finance asks for them at audit time;
- any other copy may be deleted.
