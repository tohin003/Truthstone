# Known issues

## test/rates-2027.test.ts fails until mid-December

Nordpaket publishes next year's rate card in mid-December. Until then there is no
`data/rate-cards/2027.json`, and `test/rates-2027.test.ts` fails with `RateError: no rate card
for 2027`. That is expected: the test is the reminder to add the card before January, so it is
deliberately not skipped. Do not add a placeholder card: quotes would use made-up prices.
Owner: Jonas (logistics).
