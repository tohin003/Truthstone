import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

test("a booking carries the reference, destination and billable weight", () => {
  const body = bookingRequest(quote({ country: "de", postcode: "10 115", parcel }), "ORD-1001");
  assert.equal(body.reference, "ORD-1001");
  assert.equal(body.service, "parcel");
  assert.deepEqual(body.destination, { country: "DE", postcode: "10115" });
  assert.equal(body.billableWeightKg, "2.5");
  assert.equal(body.currency, "EUR");
});

test("charges and the total are sent as euro amounts", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel }), "ORD-1001");
  assert.equal(body.charges.length, 2);
  assert.equal(body.charges[0].code, "base");
  assert.equal(body.charges[0].amount, "6.90");
  assert.equal(body.charges[1].code, "fuel");
  assert.equal(body.charges[1].amount, "0.59");
  assert.equal(body.total, "7.49");
});

test("malformed booking references are refused", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel });
  assert.throws(() => bookingRequest(q, "ORD 1001"), RangeError);
  assert.throws(() => bookingRequest(q, "AB"), RangeError);
  assert.throws(() => bookingRequest(q, "ORD-" + "9".repeat(29)), RangeError);
});

// QA acceptance test for SHOP-412: from November 2026 the shop's order numbers are lower case.
test("SHOP-412: new-style order numbers are booked as they are", () => {
  const body = bookingRequest(quote({ country: "DE", postcode: "10115", parcel }), "ord-2026-1001");
  assert.equal(body.reference, "ord-2026-1001");
  assert.equal(body.total, "7.49");
});
