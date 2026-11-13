# Known issues

Tests that fail on main on purpose until the issue behind them is decided. Leave them alone
in unrelated changes: the fix belongs to the issue.

## #73 Oversize surcharge to Austria

Nordpaket's draft contract for 2027 charges €18.00 instead of €12.00 for oversize parcels to
Austria (zone 4). Finance has not signed it, and it may still change or start mid-year, so the
README's €12.00 applies to every zone until #73 is decided.

`test/oversize-austria.test.ts` records the draft rule and fails until then. Please don't
"fix" it as part of other changes: the surcharge change, its date and the rate-card work belong
to #73.
