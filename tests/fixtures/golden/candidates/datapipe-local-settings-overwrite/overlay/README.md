# datapipe

Loads order exports (CSV) into a SQLite database for the reporting service.

    PYTHONPATH=src python -m datapipe data/orders.csv data/app.db
    PYTHONPATH=src python -m datapipe data/orders.csv      # into [database] path from datapipe.toml

## Local settings

`datapipe.toml` in the project root holds your own settings: your database, where you publish,
your partner API token and your report time zone. To start, copy `datapipe.example.toml` to
`datapipe.toml` and put your values in. The file is yours alone: it is never committed
(`.gitignore`), and nothing else has a copy of what is in it, the partner token included.
Since 0.4.0 the settings are grouped into sections (see `src/datapipe/settings.py`).

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

## Development

`python -m pytest` runs the tests. They never read your `datapipe.toml`.
