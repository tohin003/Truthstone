// SHIP-318: Nordpaket's billing for bulky parcels, from the account manager's email of 2026-10-30
// ("for the 2026 contract, volumetric weight is length x width x height in cm divided by 4000").
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

test("SHIP-318: volumetric weight uses the 2026 contract's divisor of 4000", () => {
  assert.equal(volumetricWeight(box(1, 40, 30, 20)), 6);
  assert.equal(volumetricWeight(box(1, 50, 40, 30)), 15);
});

test("SHIP-318: a light, bulky parcel is billed by its contract volumetric weight", () => {
  assert.equal(billableWeight(box(1, 40, 30, 20)), 6);
  const q = quote({ country: "DE", postcode: "10115", parcel: box(1, 40, 30, 20) });
  assert.equal(q.billableKg, 6);
  assert.equal(q.lines[0].amountCents, 890); // zone 1, up to 10 kg
});
