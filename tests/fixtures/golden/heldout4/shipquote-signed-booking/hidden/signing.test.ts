import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";
import { signBooking } from "../src/signing.ts";
import * as shipquote from "../src/index.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const berlin = () => bookingRequest(quote({ country: "DE", postcode: "10115", parcel: small }), "ORD-1001");

const BERLIN_PAYLOAD =
  '{"billableWeightKg":"2.5","charges":[{"amount":"6.90","code":"base","label":"Base rate, zone 1 (Germany North & East), up to 5 kg"},' +
  '{"amount":"0.59","code":"fuel","label":"Fuel surcharge 8.5%"}],"currency":"EUR","destination":{"country":"DE","postcode":"10115"},' +
  '"reference":"ORD-1001","service":"parcel","total":"7.49"}';
const BERLIN_SIGNATURE = "v1=8bf419b64916c90f58922c405583523bcab9b03ecfb61db65fbf407ab5175b98";

test("the payload is the booking as canonical JSON", () => {
  assert.equal(signBooking(berlin(), "np_test_5f3a9c", 1762425600).payload, BERLIN_PAYLOAD);
});

test("the headers carry the timestamp and the v1 HMAC-SHA256 signature", () => {
  assert.deepEqual(signBooking(berlin(), "np_test_5f3a9c", 1762425600).headers, {
    "X-Nordpaket-Timestamp": "1762425600",
    "X-Nordpaket-Signature": BERLIN_SIGNATURE,
  });
});

test("an oversize parcel to a remote Austrian postcode: four charges, kept in order", () => {
  const parcel = { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 };
  const body = bookingRequest(quote({ country: "AT", postcode: "6561", parcel }), "ORD-2077");
  const signed = signBooking(body, "kiosk-secret-2026", 1762512345);
  assert.equal(
    signed.payload,
    '{"billableWeightKg":"16.0","charges":[{"amount":"26.90","code":"base","label":"Base rate, zone 4 (Austria), up to 20 kg"},' +
      '{"amount":"2.29","code":"fuel","label":"Fuel surcharge 8.5%"},{"amount":"6.90","code":"remote","label":"Remote area surcharge"},' +
      '{"amount":"12.00","code":"oversize","label":"Oversize surcharge"}],"currency":"EUR","destination":{"country":"AT","postcode":"6561"},' +
      '"reference":"ORD-2077","service":"parcel","total":"48.09"}',
  );
  assert.equal(signed.headers["X-Nordpaket-Signature"], "v1=4be4edaa747ead3ea884c3e8917d276bfb78a9434ceb5f8ae80975fab639d0e1");
  assert.equal(signed.headers["X-Nordpaket-Timestamp"], "1762512345");
});

test("key order in the body does not matter, at any level", () => {
  const original = berlin();
  const shuffled = {
    total: original.total,
    currency: original.currency,
    charges: original.charges.map(({ code, label, amount }) => ({ amount, label, code })),
    billableWeightKg: original.billableWeightKg,
    destination: { postcode: original.destination.postcode, country: original.destination.country },
    service: original.service,
    reference: original.reference,
  };
  const signed = signBooking(shuffled, "np_test_5f3a9c", 1762425600);
  assert.equal(signed.payload, BERLIN_PAYLOAD);
  assert.equal(signed.headers["X-Nordpaket-Signature"], BERLIN_SIGNATURE);
});

test("an empty secret or a timestamp that is not a positive whole number is refused", () => {
  assert.throws(() => signBooking(berlin(), "", 1762425600), RangeError);
  assert.throws(() => signBooking(berlin(), "np_test_5f3a9c", 0), RangeError);
  assert.throws(() => signBooking(berlin(), "np_test_5f3a9c", -60), RangeError);
  assert.throws(() => signBooking(berlin(), "np_test_5f3a9c", 1762425600.5), RangeError);
  assert.throws(() => signBooking(berlin(), "np_test_5f3a9c", Number.NaN), RangeError);
});

test("signBooking is part of the public API", () => {
  assert.equal(typeof (shipquote as Record<string, unknown>).signBooking, "function");
});
