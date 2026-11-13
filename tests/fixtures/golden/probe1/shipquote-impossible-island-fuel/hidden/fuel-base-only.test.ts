import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("a German island delivery: fuel on the base rate only, plus the remote surcharge", () => {
  const q = quote({ country: "DE", postcode: "18565", parcel: box(2.3, 20, 15, 10) });
  assert.deepEqual(amounts(q), { base: 690, fuel: 59, remote: 450 });
  assert.equal(q.totalCents, 1199);
});

test("an Austrian remote area: fuel on the base rate only", () => {
  const q = quote({ country: "AT", postcode: "6561", parcel: box(2.3, 20, 15, 10) });
  assert.deepEqual(amounts(q), { base: 1590, fuel: 136, remote: 690 });
  assert.equal(q.totalCents, 2416);
});

test("a southern remote area: fuel on the base rate only", () => {
  const q = quote({ country: "DE", postcode: "87561", parcel: box(0.8, 20, 15, 10) });
  assert.deepEqual(amounts(q), { base: 590, fuel: 51, remote: 350 });
  assert.equal(q.totalCents, 991);
});

test("oversize and ordinary quotes are unchanged", () => {
  const big = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });
  assert.deepEqual(amounts(big), { base: 1490, fuel: 127, oversize: 1200 });
  const small = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  assert.deepEqual(amounts(small), { base: 690, fuel: 59 });
  assert.equal(small.totalCents, 749);
});

test("the booking request for an island parcel carries the base-only fuel", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "25980", parcel: box(2.3, 20, 15, 10) }), "SO-1001");
  assert.deepEqual(
    body.charges.map((charge) => [charge.code, charge.amount]),
    [
      ["base", "6.90"],
      ["fuel", "0.59"],
      ["remote", "4.50"],
    ],
  );
  assert.equal(body.total, "11.99");
});
