import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const insured = (declaredValueCents: number, postcode = "10115", country = "DE") =>
  quote({ country, postcode, parcel, declaredValueCents } as never);
const insurance = (q: ReturnType<typeof quote>) => q.lines.find((line) => line.code === ("insurance" as never));

test("insurance is 1.2% of the declared value, rounded up to the cent, between €2.50 and €40.00", () => {
  for (const [value, cents] of [[30000, 360], [33333, 400], [20834, 251], [20833, 250], [10000, 250], [1, 250], [500000, 4000], [333334, 4000]]) {
    const line = insurance(insured(value));
    assert.equal(line?.amountCents, cents, String(value));
  }
});

test("the insurance line is the last line, labelled with the declared value, and counts in the total", () => {
  const q = insured(30000);
  const last = q.lines[q.lines.length - 1];
  assert.equal(last.code, "insurance");
  assert.equal(last.label, "Insurance (declared value €300.00)");
  assert.equal(q.totalCents, 690 + 59 + 360);
  const remote = insured(30000, "18565"); // Hiddensee: remote area, zone 1
  assert.equal(remote.lines[remote.lines.length - 1].code, "insurance");
});

test("no declared value, no insurance line", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel });
  assert.equal(insurance(q), undefined);
  assert.equal(q.totalCents, 749);
});

test("insurance is not available to Austria, and declared values must be whole positive cents", () => {
  assert.throws(() => insured(30000, "1010", "AT"), RangeError);
  for (const bad of [0, -100, 12.5, Number.NaN]) {
    assert.throws(() => insured(bad), RangeError, String(bad));
  }
});

test("bookings carry the insurance charge", () => {
  const body = bookingRequest(insured(30000), "ORD-1001");
  assert.deepEqual(body.charges.map((charge) => charge.code), ["base", "fuel", "insurance"]);
  assert.equal(body.charges[2].amount, "3.60");
  assert.equal(body.total, "11.09");
});
