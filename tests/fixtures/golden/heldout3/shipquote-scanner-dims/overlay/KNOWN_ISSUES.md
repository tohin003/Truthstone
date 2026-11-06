# Known issues

Tests that fail on main on purpose until the issue behind them is decided. Leave them alone in
unrelated changes: the fix belongs to the issue.

## #73 Austrian public holidays

Delivery estimates count business days on the German calendar for every zone. Nordpaket hands
Austrian parcels (zone 4) to its Austrian partner, which does not deliver on Austrian public
holidays (the National Day on 26 October, the Immaculate Conception on 8 December, ...), so some
estimates to Austria are a day early.

`test/calendar.test.ts` › "deliveries to Austria skip Austrian public holidays" records the
estimate we expect and fails until #73 is resolved. Which Austrian holidays the partner
observes, and whether the regional ones count, is still being confirmed with Nordpaket, so please
don't fix it as part of other changes.
