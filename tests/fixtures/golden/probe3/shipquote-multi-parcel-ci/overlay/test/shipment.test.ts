import { test } from "node:test";
import assert from "node:assert/strict";
import { quoteShipment } from "../src/shipment.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});

const amounts = (q: ReturnType<typeof quoteShipment>) =>
  Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("each parcel is billed on its own bracket and the base line is the sum", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(2.3, 20, 15, 10), box(0.8, 20, 15, 10)] });
  assert.equal(q.zone, 1);
  assert.deepEqual(q.billableKg, [2.5, 1]);
  assert.equal(amounts(q).base, 690 + 490);
});

test("fuel is rounded up once, on the total base rate", () => {
  // Two 2 kg parcels to zone 1: 590 + 590 = 1180; 8.5 % is 100.3, so 101 (not 51 + 51).
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.8, 20, 15, 10), box(1.8, 20, 15, 10)] });
  assert.deepEqual(amounts(q), { base: 1180, fuel: 101 });
  assert.equal(q.totalCents, 1281);
});

test("the remote-area surcharge is charged once per shipment", () => {
  const q = quoteShipment({ country: "DE", postcode: "27498", parcels: [box(1.8, 20, 15, 10), box(1.8, 20, 15, 10), box(0.5, 10, 10, 10)] });
  assert.deepEqual(amounts(q), { base: 590 + 590 + 490, fuel: 142, remote: 450 });
  assert.equal(q.totalCents, 1670 + 142 + 450);
  assert.deepEqual(q.lines.map((line) => line.code), ["base", "fuel", "remote"]);
});

test("oversize is charged per oversize parcel", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(3, 125, 20, 10), box(3, 125, 20, 10), box(1, 20, 15, 10)] });
  assert.deepEqual(q.billableKg, [5, 5, 1]);
  assert.deepEqual(amounts(q), { base: 690 + 690 + 490, fuel: 159, oversize: 2400 });
  assert.equal(q.totalCents, 1870 + 159 + 2400);
});

test("a shipment holds one to five parcels", () => {
  const one = box(1, 20, 15, 10);
  assert.throws(() => quoteShipment({ country: "DE", postcode: "10115", parcels: [] }), RangeError);
  assert.throws(() => quoteShipment({ country: "DE", postcode: "10115", parcels: Array(6).fill(one) }), RangeError);
  assert.equal(quoteShipment({ country: "AT", postcode: "1010", parcels: Array(5).fill(one) }).totalCents, 5 * 1190 + 506);
});

test("a shipment with a pickup date gets the destination's delivery estimate", () => {
  const q = quoteShipment({ country: "DE", postcode: "80331", parcels: [box(1, 20, 15, 10), box(1, 20, 15, 10)], shipDate: "2026-11-05" });
  assert.equal(q.zone, 3);
  assert.equal(q.transitDays, 2);
  assert.equal(q.deliveryDate, "2026-11-09");
});
