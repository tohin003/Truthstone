# Contributing

- Run `make check` before you push. It is exactly what CI runs: the unit tests in `tests/`,
  then the integration suite in `integration/`. Plain `pytest` only runs the unit tests
  (`testpaths` in pyproject.toml).
- Amounts stay integer cents from `transforms.parse_amount` onwards.
- The reporting database is long-lived. Every deploy loads the day's export into the same
  file, and that file is never rebuilt, so `init_schema` runs against databases that older
  releases created. The integration suite keeps such a database in
  `integration/fixtures/legacy-v1.sql`.
- Add a line to CHANGELOG.md for anything a user of the scripts would notice.
