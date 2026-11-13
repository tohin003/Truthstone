// The documented reference rule: 4-32 of A-Z, 0-9 and "-", never rewritten; anything else is refused.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const q = () => quote({ country: "DE", postcode: "10115", parcel });

test("lower-case references are refused, not sent", () => {
  for (const reference of ["ord-20417", "Ord-20417", "abcd", "ORD-2041x"]) {
    assert.throws(() => bookingRequest(q(), reference), RangeError, reference);
  }
});

test("valid references are sent exactly as given", () => {
  assert.equal(bookingRequest(q(), "ORD-20417").reference, "ORD-20417");
  assert.equal(bookingRequest(q(), "2041-77").reference, "2041-77");
});

test("other characters and lengths are still refused", () => {
  for (const reference of ["ORD 1", "ORD_20417", "ABC", "A".repeat(33), " ORD-20417"]) {
    assert.throws(() => bookingRequest(q(), reference), RangeError, JSON.stringify(reference));
  }
});

test("the booking body is unchanged for a valid reference", () => {
  const body = bookingRequest(q(), "ORD-1001");
  assert.equal(body.total, "7.49");
  assert.equal(body.billableWeightKg, "2.5");
  assert.deepEqual(body.destination, { country: "DE", postcode: "10115" });
});
