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

A row that cannot be read (a bad quantity, timestamp or amount) stops the import with an error,
and nothing from that export is loaded.

## Import summary

Every import prints one summary line, `read 12 row(s): 9 inserted, 2 duplicate(s) dropped,
1 already present`, from `pipeline.ImportSummary`:

| field             | meaning                                                         |
|-------------------|-----------------------------------------------------------------|
| `rows_read`       | every non-blank data row in the export                          |
| `duplicates`      | rows repeating an `order_id` seen earlier in the same export    |
| `inserted`        | orders this import stored                                       |
| `already_present` | orders the database already had                                 |

`inserted + duplicates + already_present == rows_read` for every import. The reporting
dashboard checks that sum on each entry of the import log and pages on-call when it does not
hold, because a gap means orders went missing between the export and the database.

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.
