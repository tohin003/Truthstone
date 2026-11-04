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

## Excel exports

Finance often opens an export in Excel (German locale) and saves it again before it reaches
us. Those files are loaded as they are:

- UTF-8 with a byte-order mark; the mark is ignored in any export;
- `;` as the delimiter, recognised from the header line;
- Windows line endings, and line breaks inside quoted cells (kept as `\n`);
- amounts with a decimal comma and `.` between thousands: `1.240,50`, `-3,99`, `7`;
- timestamps the way Excel rewrites them, `DD.MM.YYYY HH:MM` (UTC; Excel drops the
  seconds), as well as the usual `2026-10-01T08:12:00Z`.

In comma-separated exports nothing changes: there a comma separates thousands (`$1,240.00`).

## Scripts

- `scripts/deploy.sh` loads an export and publishes the database to `$DEPLOY_TARGET`.
- `scripts/backup.sh` copies the database into `backups/` under a timestamped name.

## Development

CI runs `pytest` on every push, and main has to be green before a release is tagged. The
tests in `tests/` are the specification of the export formats; the files in
`tests/fixtures/` are real exports from finance, with customer data replaced.
