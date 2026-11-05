import { test } from "node:test";
import assert from "node:assert/strict";
import { billableWeight, ParcelError } from "../src/parcel.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number) => ({ weightKg, lengthCm: 60, widthCm: 40, heightCm: 40 });

test("parcels over 31.5 kg billable are refused, by billableWeight and by quote", () => {
  for (const kg of [31.6, 38, 50]) {
    assert.throws(() => billableWeight(box(kg)), ParcelError, String(kg));
    assert.throws(() => quote({ country: "DE", postcode: "10115", parcel: box(kg) }), ParcelError, String(kg));
  }
});

test("31.5 kg is still quoted at the top bracket", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(31.5) });
  assert.equal(q.billableKg, 31.5);
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel"]);
  assert.equal(q.lines[0].amountCents, 1690);
});
