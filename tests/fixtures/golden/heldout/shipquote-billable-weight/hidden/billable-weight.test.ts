import { test } from "node:test";
import assert from "node:assert/strict";
import { billableWeight, ParcelError } from "../src/parcel.ts";
import { quote } from "../src/quote.ts";
import { fuelSurcharge } from "../src/surcharges.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("weights are billed to the gram", () => {
  assert.equal(billableWeight(box(1.501, 10, 10, 5)), 2);
  assert.equal(billableWeight(box(0.501, 10, 10, 5)), 1);
  assert.equal(billableWeight(box(2.001, 10, 10, 5)), 2.5);
  assert.equal(billableWeight(box(9.999, 10, 10, 5)), 10);
  assert.equal(billableWeight(box(31.499, 10, 10, 5)), 31.5);
});

test("a gram over the limit is refused", () => {
  assert.throws(() => billableWeight(box(31.501, 10, 10, 5)), ParcelError);
});

test("weights on a step, and ordinary weights, are billed as before", () => {
  assert.equal(billableWeight(box(1.5, 10, 10, 5)), 1.5);
  assert.equal(billableWeight(box(2.3, 20, 15, 10)), 2.5);
  assert.equal(billableWeight(box(1, 40, 30, 20)), 5);
  assert.equal(billableWeight(box(0.2, 10, 10, 5)), 0.5);
});

test("a gram-precise weight is quoted in the right bracket", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(1.001, 10, 10, 5) });
  assert.equal(q.billableKg, 1.5);
  assert.deepEqual(amounts(q), { base: 590, fuel: 51 });
});

test("fuel on an exact amount is still not rounded up a cent by float noise", () => {
  assert.equal(fuelSurcharge(1400), 119);
  const q = quote({ country: "DE", postcode: "50667", parcel: box(18, 50, 40, 30) });
  assert.deepEqual(amounts(q), { base: 1400, fuel: 119 });
  assert.equal(q.totalCents, 1519);
  assert.equal(quote({ country: "DE", postcode: "30159", parcel: box(12.25, 30, 30, 30) }).totalCents, 1519);
});

test("other fuel amounts still round up to the next cent", () => {
  assert.equal(fuelSurcharge(490), 42);
  assert.equal(fuelSurcharge(1690), 144);
  assert.equal(quote({ country: "AT", postcode: "1010", parcel: box(4.2, 30, 30, 30) }).totalCents, 2160);
  assert.equal(quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) }).totalCents, 2817);
});
