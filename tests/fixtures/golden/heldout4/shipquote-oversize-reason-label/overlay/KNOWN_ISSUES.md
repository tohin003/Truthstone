# Known issues

Tests that fail on main on purpose until the decision behind them is made. Leave them alone in
unrelated changes: the fix belongs to the issue.

## #52 Thousands separators in amounts

`parseEuros` rejects amounts written with a thousands separator, such as `1.234,56`, which the
warehouse's stock-sheet exports contain. Finance has not decided how to read them: `1.234,56` looks
clear, but `1.234` could be 1234 euros (German style) or a typo for 1.23, and `parseEuros` already
takes a comma as the decimal mark (`7,49`). The test "parseEuros reads a thousands separator" in
`test/money.test.ts` records one candidate rule and fails until #52 is decided. Please don't fix it
as part of other changes.
