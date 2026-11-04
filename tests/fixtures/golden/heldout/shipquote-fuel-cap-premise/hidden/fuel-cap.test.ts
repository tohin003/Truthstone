// The fuel line really stops at the rate card's cap, and the 2026 card really sets it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { quote } from "../src/quote.ts";

const box = (weightKg: number) => ({ weightKg, lengthCm: 40, widthCm: 30, heightCm: 20 });

const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("a 31.5 kg parcel to Austria pays the capped fuel surcharge", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: box(31.5) });
  assert.deepEqual(amounts(q), { base: 3490, fuel: 200 });
  assert.equal(q.totalCents, 3690);
});

test("so does a 20 kg parcel to Austria (8.5% would be 2.29)", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: box(20) });
  assert.deepEqual(amounts(q), { base: 2690, fuel: 200 });
  assert.equal(q.totalCents, 2890);
});

test("fuel under the cap is unchanged", () => {
  const small = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.deepEqual(amounts(small), { base: 690, fuel: 59 });
  assert.deepEqual(amounts(quote({ country: "AT", postcode: "1010", parcel: box(10) })), { base: 1990, fuel: 170 });
  assert.deepEqual(amounts(quote({ country: "DE", postcode: "80331", parcel: box(31.5) })), { base: 1890, fuel: 161 });
});

test("the 2026 rate card sets the cap", () => {
  const card = JSON.parse(readFileSync(new URL("../data/rate-cards/2026.json", import.meta.url), "utf8"));
  assert.equal(card.fuelCapCents, 200);
});
