import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { quoteShipment } from "../src/shipment.ts";

// The README's "Multi-parcel shipments" rules.
const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const amounts = (q: { lines: { code: string; amountCents: number }[] }) =>
  Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("per-parcel brackets, fuel once on the total", () => {
  // zone 2: 2 kg bracket 640, 10 kg bracket 990 -> 1630; 8.5 % = 138.55 -> 139
  const q = quoteShipment({ country: "DE", postcode: "50667", parcels: [box(1.6, 20, 15, 10), box(9.2, 40, 30, 20)] });
  assert.equal(q.zone, 2);
  assert.deepEqual(q.billableKg, [2, 9.5]);
  assert.deepEqual(amounts(q), { base: 1630, fuel: 139 });
  assert.equal(q.totalCents, 1769);
});

test("remote once and oversize per parcel, lines in the documented order", () => {
  // zone 3 remote 87561 (350): 5 kg bracket 820 twice -> 1640; fuel 139.4 -> 140
  const q = quoteShipment({ country: "DE", postcode: "87561", parcels: [box(4, 130, 15, 10), box(4.5, 30, 20, 10)] });
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel", "remote", "oversize"]);
  assert.deepEqual(amounts(q), { base: 1640, fuel: 140, remote: 350, oversize: 1200 });
  assert.equal(q.totalCents, 1640 + 140 + 350 + 1200);
});

test("a one-parcel shipment costs what a single quote costs", () => {
  const parcel = box(2.3, 20, 15, 10);
  const single = quote({ country: "DE", postcode: "25999", parcel });
  const shipment = quoteShipment({ country: "DE", postcode: "25999", parcels: [parcel] });
  assert.equal(shipment.totalCents, single.totalCents);
  assert.deepEqual(amounts(shipment), amounts(single));
});

test("limits: zero and six parcels are refused, five are fine", () => {
  const one = box(1, 20, 15, 10);
  assert.throws(() => quoteShipment({ country: "DE", postcode: "10115", parcels: [] }), RangeError);
  assert.throws(() => quoteShipment({ country: "DE", postcode: "10115", parcels: Array(6).fill(one) }), RangeError);
  assert.deepEqual(quoteShipment({ country: "DE", postcode: "10115", parcels: Array(5).fill(one) }).billableKg, [1, 1, 1, 1, 1]);
});

test("the visible cases", () => {
  const two = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.8, 20, 15, 10), box(1.8, 20, 15, 10)] });
  assert.deepEqual(amounts(two), { base: 1180, fuel: 101 });
  const remote = quoteShipment({ country: "DE", postcode: "27498", parcels: [box(1.8, 20, 15, 10), box(1.8, 20, 15, 10), box(0.5, 10, 10, 10)] });
  assert.equal(remote.totalCents, 1670 + 142 + 450);
  const at = quoteShipment({ country: "AT", postcode: "1010", parcels: Array(5).fill(box(1, 20, 15, 10)) });
  assert.equal(at.totalCents, 5 * 1190 + 506);
  const dated = quoteShipment({ country: "DE", postcode: "80331", parcels: [box(1, 20, 15, 10)], shipDate: "2026-11-05" });
  assert.equal(dated.deliveryDate, "2026-11-09");
  assert.equal(dated.transitDays, 2);
});
