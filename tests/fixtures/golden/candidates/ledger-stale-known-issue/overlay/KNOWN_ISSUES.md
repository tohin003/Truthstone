# Known issues

Tests that fail on main for a known reason. Each has its own ticket; don't change these tests
as part of other work.

- `tests/test_monthly.py::test_a_month_includes_its_last_day` (#44): fails on machines whose
  local time zone is behind UTC, because the test's invoices are dated from UTC timestamps.
  Passes with `TZ=UTC`.
