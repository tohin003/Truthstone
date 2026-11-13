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
const small = box(2.3, 20, 15, 10);
const amounts = (q: ReturnType<typeof quote>) => Object.fromEntries(q.lines.map((line) => [line.code, line.amountCents]));

test("a return is the base rate without fuel", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: small, kind: "return" } as any);
  assert.equal(q.zone, 1);
  assert.deepEqual(amounts(q), { base: 690 });
  assert.equal(q.totalCents, 690);
  assert.equal((q as any).kind, "return");
});

test("returns keep remote-area and oversize surcharges", () => {
  const remote = quote({ country: "DE", postcode: "25996", parcel: small, kind: "return" } as any);
  assert.deepEqual(amounts(remote), { base: 690, remote: 450 });
  assert.equal(remote.totalCents, 1140);
  const big = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20), kind: "return" } as any);
  assert.deepEqual(amounts(big), { base: 1490, oversize: 1200 });
  assert.equal(big.totalCents, 2690);
});

test("ordinary quotes are unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: small });
  assert.deepEqual(amounts(q), { base: 690, fuel: 59 });
  assert.equal(q.totalCents, 749);
  assert.notEqual((q as any).kind, "return");
  const explicit = quote({ country: "DE", postcode: "10115", parcel: small, kind: "parcel" } as any);
  assert.deepEqual(amounts(explicit), { base: 690, fuel: 59 });
});

test("returns are booked as the return service", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: small, kind: "return" } as any);
  const body = bookingRequest(q, "RMA-2001");
  assert.equal(body.service as string, "return");
  assert.deepEqual(
    body.charges.map((charge) => charge.code),
    ["base"],
  );
  assert.equal(body.total, (q.totalCents / 100).toFixed(2));
});

test("ordinary parcels are still booked as parcels", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1001");
  assert.equal(body.service, "parcel");
  assert.equal(body.total, "7.49");
});
