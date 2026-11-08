import { test } from "node:test";
import assert from "node:assert/strict";
import { crc32 } from "node:zlib";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
// The checksum is a new field; older type definitions do not know it.
type Signed = Record<string, unknown> & { checksum?: unknown };
const sign = (q: ReturnType<typeof quote>, reference: string) => bookingRequest(q, reference) as unknown as Signed;
// The carrier's check: CRC-32 (zlib/zip/PNG) of JSON.stringify(body without checksum), UTF-8, 8 hex digits.
const expected = (body: Signed) => {
  const { checksum: _checksum, ...rest } = body;
  return crc32(Buffer.from(JSON.stringify(rest), "utf8")).toString(16).padStart(8, "0");
};

test("every booking request carries a checksum of 8 lower-case hex digits", () => {
  const body = sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1001");
  assert.equal(typeof body.checksum, "string");
  assert.match(body.checksum as string, /^[0-9a-f]{8}$/);
});

test("the checksum is the CRC-32 of the rest of the body as JSON", () => {
  const body = sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1001");
  assert.equal(body.checksum, expected(body));
});

test("a checksum with leading zeros keeps all eight digits", () => {
  // As the request's body is built today, this reference's CRC-32 is 0x06c0ad2e.
  const body = sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1022");
  assert.match(body.checksum as string, /^[0-9a-f]{8}$/);
  assert.equal(body.checksum, expected(body));
});

test("the checksum follows the body: other destinations, surcharges and references", () => {
  const bodies = [
    sign(quote({ country: "AT", postcode: "6456", parcel: small }), "ORD-2001"),
    sign(quote({ country: "DE", postcode: "80331", parcel: { weightKg: 12, lengthCm: 130, widthCm: 40, heightCm: 30 } }), "ORD-2002"),
    sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-2003"),
    sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-2004"),
  ];
  for (const body of bodies) {
    assert.equal(body.checksum, expected(body));
  }
  assert.notEqual(bodies[2].checksum, bodies[3].checksum);
});

test("the rest of the booking request is unchanged", () => {
  const body = sign(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1001");
  const { checksum: _checksum, ...rest } = body;
  assert.deepEqual(rest, {
    reference: "ORD-1001",
    service: "parcel",
    destination: { country: "DE", postcode: "10115" },
    billableWeightKg: "2.5",
    charges: [
      { code: "base", label: "Base rate, zone 1 (Germany North & East), up to 5 kg", amount: "6.90" },
      { code: "fuel", label: "Fuel surcharge 8.5%", amount: "0.59" },
    ],
    total: "7.49",
    currency: "EUR",
  });
  assert.throws(() => bookingRequest(quote({ country: "DE", postcode: "10115", parcel: small }), "ord 1"), RangeError);
});
