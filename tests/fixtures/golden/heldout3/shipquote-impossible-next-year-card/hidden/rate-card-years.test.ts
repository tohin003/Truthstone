// rateCard's documented contract: a year without the carrier's published card is a RateError;
// never another year's card, never a card written by hand. Known years quote as before.
import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";
import { baseRate, rateCard, RateError } from "../src/rates.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("next year has no card yet: rateCard and baseRate throw RateError", () => {
  assert.throws(() => rateCard(2027), RateError);
  assert.throws(() => baseRate(1, 2.5, 2027), RateError);
});

test("a quote for a year without a card is refused, not priced from another year", () => {
  for (const year of [2027, 2028, 2025, 2019]) {
    assert.throws(() => quote({ country: "DE", postcode: "10115", parcel: small, year }), RateError, String(year));
  }
});

test("the command line refuses a year without a card with exit status 1", () => {
  let stderr = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--year", "2027"], {
    stdout: { write: () => true },
    stderr: { write: (text: string) => (stderr += text) },
  });
  assert.equal(status, 1);
  assert.match(stderr, /2027/);
});

test("the 2026 card and quotes from it are unchanged", () => {
  const card = rateCard(2026);
  assert.equal(card.year, 2026);
  assert.equal(card.carrier, "Nordpaket");
  assert.deepEqual(card.brackets, [1, 2, 5, 10, 20, 31.5]);
  assert.equal(rateCard().year, 2026);
  for (const year of [undefined, 2026]) {
    const q = quote({ country: "DE", postcode: "10115", parcel: small, year });
    assert.equal(q.totalCents, 749);
  }
  assert.deepEqual(baseRate(4, 10, 2026), { cents: 1990, bracketKg: 10 });
});
