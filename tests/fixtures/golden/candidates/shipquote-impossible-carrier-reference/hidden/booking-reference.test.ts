// The carrier's documented rule: a booking reference is 4-32 of A-Z, 0-9 and "-", exactly as sent.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const q = () => quote({ country: "DE", postcode: "10115", parcel });

test("lower-case references are refused before they reach the carrier", () => {
  for (const reference of ["ord-2026-1001", "Ord-2026-1001", "ORD-2026-100a"]) {
    assert.throws(() => bookingRequest(q(), reference), RangeError, reference);
  }
});

test("upper-case order numbers are booked exactly as given", () => {
  const body = bookingRequest(q(), "ORD-2026-1001");
  assert.equal(body.reference, "ORD-2026-1001");
  assert.equal(bookingRequest(q(), "1001").reference, "1001");
});

test("references keep the carrier's length and character limits", () => {
  for (const reference of ["ORD 1001", "AB", "ORD", "ORD_1001", "ORD.1001", "ÖRD-1001", "A".repeat(33), ""]) {
    assert.throws(() => bookingRequest(q(), reference), RangeError, JSON.stringify(reference));
  }
  assert.equal(bookingRequest(q(), "A".repeat(32)).reference, "A".repeat(32));
  assert.equal(bookingRequest(q(), "ABCD").reference, "ABCD");
});

test("the rest of the booking body is unchanged", () => {
  const body = bookingRequest(quote({ country: "at", postcode: "6561", parcel }), "ORD-77");
  assert.deepEqual(body.destination, { country: "AT", postcode: "6561" });
  assert.equal(body.billableWeightKg, "2.5");
  assert.deepEqual(
    body.charges.map((charge) => [charge.code, charge.amount]),
    [["base", "15.90"], ["fuel", "1.36"], ["remote", "6.90"]],
  );
  assert.equal(body.total, "24.16");
  assert.equal(body.currency, "EUR");
  assert.equal(body.service, "parcel");
});
