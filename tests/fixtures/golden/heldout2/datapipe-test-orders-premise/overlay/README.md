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

## Settings

`python -m datapipe` (and `scripts/deploy.sh`) reads its import settings from `datapipe.cfg` in
the working directory, or from the file `$DATAPIPE_CONFIG` names:

    [import]
    default_region = CA        ; region code for orders exported without one
    source_name = shop-export  ; recorded in the imports table instead of the file name

A missing file, section or key means the default (no region, the export's file name).
`pipeline.run` takes the settings as an argument (`datapipe.config.load()` reads them).

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
