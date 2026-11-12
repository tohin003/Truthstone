import { test } from "node:test";
import assert from "node:assert/strict";
import { quote } from "../src/quote.ts";
import { RateError } from "../src/rates.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});

const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("a small parcel within Germany: base rate plus fuel", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.equal(q.zone, 1);
  assert.equal(q.billableKg, 2.5);
  assert.deepEqual(amounts(q), { base: 690, fuel: 59 });
  assert.equal(q.totalCents, 749);
  assert.equal(q.currency, "EUR");
});

test("fuel on an exact amount is not rounded up a cent by float noise", () => {
  // 1400 * 0.085 is 119.00000000000001 in binary floating point; the carrier bills 119.
  const q = quote({ country: "DE", postcode: "50667", parcel: box(18, 50, 40, 30) });
  assert.equal(q.zone, 2);
  assert.equal(q.billableKg, 18);
  assert.deepEqual(amounts(q), { base: 1400, fuel: 119 });
  assert.equal(q.totalCents, 1519);
});

test("Austria is quoted from zone 4", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: box(4.2, 30, 30, 30) });
  assert.equal(q.zone, 4);
  assert.equal(q.billableKg, 5.5);
  assert.deepEqual(amounts(q), { base: 1990, fuel: 170 });
  assert.equal(q.totalCents, 2160);
});

test("island deliveries pay fuel on the remote-area surcharge too", () => {
  // Hiddensee (18565): base 6.90 + remote 4.50 = 11.40; 8.5% fuel on that is 0.969 -> 0.97
  const q = quote({ country: "DE", postcode: "18565", parcel: box(2.3, 20, 15, 10) });
  assert.equal(q.zone, 1);
  assert.deepEqual(amounts(q), { base: 690, fuel: 97, remote: 450 });
  assert.equal(q.totalCents, 1237);
});

test("oversize parcels get the oversize surcharge", () => {
  const q = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });
  assert.equal(q.billableKg, 16);
  assert.deepEqual(amounts(q), { base: 1490, fuel: 127, oversize: 1200 });
  assert.equal(q.totalCents, 2817);
});

test("the total is the sum of the lines", () => {
  const q = quote({ country: "DE", postcode: "70173", parcel: box(0.4, 25, 18, 4) });
  assert.equal(q.totalCents, q.lines.reduce((sum, line) => sum + line.amountCents, 0));
});

test("the base line names the zone and the weight bracket", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.equal(q.lines[0].label, "Base rate, zone 1 (Germany North & East), up to 5 kg");
  assert.equal(q.lines[1].label, "Fuel surcharge 8.5%");
});

test("a year without a rate card cannot be quoted", () => {
  assert.throws(() => quote({ country: "DE", postcode: "10115", parcel: box(1, 10, 10, 10), year: 2019 }), RateError);
});
