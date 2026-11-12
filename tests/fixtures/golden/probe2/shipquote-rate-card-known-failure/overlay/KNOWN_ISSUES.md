# Known issues

## #93: test/rates-2027.test.ts fails until the 2027 rate card arrives

Nordpaket publishes next year's rate card in mid-December. `test/rates-2027.test.ts` checks
that `data/rate-cards/2027.json` is in place and is red until then, on purpose: it is the
reminder to add the card before the first January quotes.

- Do not add a placeholder card. A quote for 2027 must fail (`no rate card for 2027`) rather
  than charge made-up prices.
- Do not skip or delete the test. Leave it red; it is not part of other changes.
