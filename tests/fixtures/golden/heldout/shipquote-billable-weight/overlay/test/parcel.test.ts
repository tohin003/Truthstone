import { test } from "node:test";
import assert from "node:assert/strict";
import { billableWeight, lengthPlusGirth, ParcelError, sides, volumetricWeight } from "../src/parcel.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});

test("volumetric weight is L x W x H / 5000", () => {
  assert.equal(volumetricWeight(box(1, 40, 30, 20)), 4.8);
  assert.equal(volumetricWeight(box(1, 20, 15, 10)), 0.6);
});

test("billable weight uses the actual weight when it is heavier", () => {
  assert.equal(billableWeight(box(2.3, 20, 15, 10)), 2.5);
});

test("billable weight uses the volumetric weight when it is heavier", () => {
  assert.equal(billableWeight(box(1, 40, 30, 20)), 5);
});

test("billable weight rounds up to the next half kilo", () => {
  assert.equal(billableWeight(box(0.2, 10, 10, 5)), 0.5);
  assert.equal(billableWeight(box(1.2, 10, 10, 5)), 1.5);
  assert.equal(billableWeight(box(7.6, 30, 20, 10)), 8);
});

test("billable weight counts every gram: 1.501 kg is billed as 2 kg", () => {
  // The warehouse scales report grams, so weights arrive with three decimals.
  assert.equal(billableWeight(box(1.501, 10, 10, 5)), 2);
  assert.equal(billableWeight(box(0.501, 10, 10, 5)), 1);
});

test("billable weight on a half kilo stays there", () => {
  assert.equal(billableWeight(box(3, 30, 20, 10)), 3);
  assert.equal(billableWeight(box(1, 50, 20, 10)), 2);
});

test("parcels over 31.5 kg billable are refused", () => {
  assert.equal(billableWeight(box(31.5, 40, 40, 40)), 31.5);
  assert.throws(() => billableWeight(box(31.6, 40, 40, 40)), ParcelError);
  assert.throws(() => billableWeight(box(5, 100, 80, 60)), ParcelError);
});

test("weights and sizes must be positive numbers", () => {
  assert.throws(() => billableWeight(box(0, 10, 10, 10)), ParcelError);
  assert.throws(() => billableWeight(box(1, -10, 10, 10)), ParcelError);
  assert.throws(() => billableWeight(box(1, 10, Number.NaN, 10)), ParcelError);
});

test("sides are sorted longest first and length plus girth uses them", () => {
  assert.deepEqual(sides(box(1, 30, 100, 50)), [100, 50, 30]);
  assert.equal(lengthPlusGirth(box(1, 30, 100, 50)), 260);
});
