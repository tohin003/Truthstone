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

## Region names

Reports show region names instead of codes: `datapipe.regions.totals_by_region(conn)`. The
names come from `data/regions.csv` (`code,name`).

## Local data

Partner exports (`exports/`), databases (`*.db`) and other CSV files under `data/` are customer
data and stay out of git (see `.gitignore`); the sample export `data/orders.csv` is the only one
committed.

## CI

CI (`.github/workflows/ci.yml`) runs `scripts/ci-local.sh` on a fresh clone. Running the same
script locally reproduces a CI run: it starts from a pristine tree, as CI does.
