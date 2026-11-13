import { test } from "node:test";
import assert from "node:assert/strict";
import { baseRate, DEFAULT_YEAR, rateCard, RateError } from "../src/rates.ts";

test("the default rate card is Nordpaket's 2026 card", () => {
  assert.equal(DEFAULT_YEAR, 2026);
  const card = rateCard();
  assert.equal(card.year, 2026);
  assert.equal(card.carrier, "Nordpaket");
  assert.deepEqual(card.brackets, [1, 2, 5, 10, 20, 31.5]);
});

test("the base rate is the first bracket the billable weight fits", () => {
  assert.deepEqual(baseRate(1, 0.5), { cents: 490, bracketKg: 1 });
  assert.deepEqual(baseRate(1, 1), { cents: 490, bracketKg: 1 });
  assert.deepEqual(baseRate(1, 1.5), { cents: 590, bracketKg: 2 });
  assert.deepEqual(baseRate(2, 5), { cents: 760, bracketKg: 5 });
  assert.deepEqual(baseRate(3, 31.5), { cents: 1890, bracketKg: 31.5 });
  assert.deepEqual(baseRate(4, 10), { cents: 1990, bracketKg: 10 });
});

test("an explicit year uses that year's card", () => {
  assert.deepEqual(baseRate(2, 20, 2026), { cents: 1400, bracketKg: 20 });
  assert.deepEqual(baseRate(1, 2.5, 2027), { cents: 730, bracketKg: 5 });
  assert.equal(rateCard(2027).year, 2027);
});

test("unknown years and weights outside the brackets are errors", () => {
  assert.throws(() => rateCard(2019), RateError);
  assert.throws(() => baseRate(1, 32), RateError);
});
