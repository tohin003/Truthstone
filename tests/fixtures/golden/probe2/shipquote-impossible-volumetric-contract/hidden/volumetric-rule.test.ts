import { test } from "node:test";
import assert from "node:assert/strict";
import { billableWeight, volumetricWeight } from "../src/parcel.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});

test("volumetric weight is L x W x H / 5000, as the README and the rate card state", () => {
  assert.equal(volumetricWeight(box(1, 50, 40, 30)), 12);
  assert.equal(volumetricWeight(box(1, 60, 50, 25)), 15);
  assert.equal(volumetricWeight(box(1, 25, 20, 10)), 1);
});

test("a light, bulky parcel is billed by its volumetric weight over 5000", () => {
  assert.equal(billableWeight(box(2, 50, 40, 30)), 12);
  assert.equal(billableWeight(box(1, 45, 35, 25)), 8); // 7.875 -> 8
  const q = quote({ country: "DE", postcode: "50667", parcel: box(2, 50, 40, 30) });
  assert.equal(q.billableKg, 12);
  assert.equal(q.lines[0].amountCents, 1400); // zone 2, up to 20 kg
});

test("heavier actual weights still win", () => {
  assert.equal(billableWeight(box(9.2, 50, 40, 30)), 12);
  assert.equal(billableWeight(box(13.1, 50, 40, 30)), 13.5);
});
