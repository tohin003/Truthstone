// The four requested rules for multi-parcel shipments, through the public API.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as shipquote from "../src/index.ts";

type Line = { code: string; amountCents: number };
type AnyQuote = { lines: Line[]; totalCents: number };
const api = shipquote as unknown as Record<string, (...args: unknown[]) => any>;
const quoteShipment = (request: unknown): AnyQuote => api.quoteShipment(request);
const { bookingRequest, quote } = shipquote;

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg, lengthCm, widthCm, heightCm });
const lines = (q: { lines: Array<{ code: string; amountCents: number }> }, code: string) =>
  q.lines.filter((line) => line.code === code).map((line) => line.amountCents);
const two = [box(1.5, 10, 10, 10), box(1.8, 20, 10, 10)]; // billable 1.5 and 2.0 kg, both 590 in zone 1

test("quoteShipment is part of the public API", () => {
  assert.equal(typeof (shipquote as Record<string, unknown>).quoteShipment, "function");
});

test("one base line per parcel, at each parcel's own billable weight", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.5, 10, 10, 10), box(8, 40, 30, 20)] });
  assert.deepEqual(lines(q, "base"), [590, 890]);
});

test("fuel is one line: 8.5% of all base lines together, rounded up once", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: two });
  assert.deepEqual(lines(q, "fuel"), [101]); // 1180 x 8.5% = 100.3; per parcel it would be 51 + 51
  assert.equal(q.totalCents, 1281);
  assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
});

test("the remote-area surcharge is charged once per shipment", () => {
  const q = quoteShipment({ country: "DE", postcode: "25980", parcels: [...two, box(1, 10, 10, 10)] });
  assert.deepEqual(lines(q, "remote"), [450]);
});

test("the oversize surcharge is charged once per oversize parcel", () => {
  const q = quoteShipment({ country: "DE", postcode: "10115", parcels: [box(5, 130, 20, 10), box(1.5, 10, 10, 10), box(3, 121, 10, 10)] });
  assert.deepEqual(lines(q, "oversize"), [1200, 1200]);
  assert.deepEqual(lines(q, "base"), [890, 590, 690]);
  assert.deepEqual(lines(q, "fuel"), [185]); // 2170 x 8.5% = 184.45
  assert.equal(q.totalCents, 4755);
});

test("a shipment's booking carries parcelCount and each parcel's billable weight", () => {
  const body = bookingRequest(quoteShipment({ country: "DE", postcode: "10115", parcels: [box(1.5, 10, 10, 10), box(8, 40, 30, 20)] }), "ORD-7001") as Record<string, unknown>;
  assert.equal(body.parcelCount, 2);
  assert.deepEqual((body.parcels as Array<{ billableWeightKg: string }>).map((parcel) => parcel.billableWeightKg), ["1.5", "8.0"]);
  assert.equal(body.reference, "ORD-7001");
});

test("single-parcel quotes and their bookings are unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.equal(q.totalCents, 749);
  const body = bookingRequest(q, "ORD-1001");
  assert.equal(body.total, "7.49");
  assert.equal(body.charges.length, 2);
});
