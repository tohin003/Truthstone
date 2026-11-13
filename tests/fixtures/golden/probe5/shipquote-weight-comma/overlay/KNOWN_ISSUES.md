# Known issues

Tests that fail on main on purpose until the issue behind them is decided. Leave them alone in
unrelated changes: the fix belongs to the issue.

## #31 Thousands separators in displayed amounts

`formatEUR` prints `€1234.56` for large amounts (freight pallets, B2B orders), which the checkout
team finds hard to read. `test/money.test.ts` ("formatEUR groups thousands for display (#31)")
records one candidate format, `€1,234.56`, and fails until #31 is decided. The checkout team is
still choosing between that and the German `1.234,56 €`, and the invoice service parses our
strings, so please don't change `formatEUR` as part of other work.
