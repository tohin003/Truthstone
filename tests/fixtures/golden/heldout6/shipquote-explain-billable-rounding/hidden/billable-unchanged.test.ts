import { test } from "node:test";
import assert from "node:assert/strict";
import { billableWeight, volumetricWeight } from "../src/parcel.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg, lengthCm, widthCm, heightCm });

test("the documented rule still holds: the greater weight, rounded up to the next 0.5 kg", () => {
  assert.equal(billableWeight(box(2.3, 20, 15, 10)), 2.5);
  assert.equal(billableWeight(box(1.2, 40, 30, 30)), 7.5);
  assert.equal(volumetricWeight(box(1.2, 40, 30, 30)), 7.2);
  assert.equal(billableWeight(box(3, 10, 10, 10)), 3);
  assert.equal(billableWeight(box(0.1, 10, 10, 10)), 0.5);
});

test("the two quotes in question are unchanged", () => {
  const small = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.equal(small.billableKg, 2.5);
  assert.equal(small.totalCents, 749);
  const bulky = quote({ country: "DE", postcode: "10115", parcel: box(1.2, 40, 30, 30) });
  assert.equal(bulky.billableKg, 7.5);
});
