// Contract with Nordpaket's Booking API v3 (schema 2026-04): the body POST /v3/bookings accepts.
// The API rejects unknown fields and prices in net euro amounts with exactly two decimals.
import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const BODY_FIELDS = ["billableWeightKg", "charges", "currency", "destination", "reference", "service", "total"];
const CHARGE_FIELDS = ["amount", "code", "label"];
const CHARGE_CODES = ["base", "fuel", "remote", "oversize"];
const AMOUNT = /^\d+\.\d{2}$/;

const parcel = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});
const quotes = [
  quote({ country: "DE", postcode: "10115", parcel: parcel(2.3, 20, 15, 10) }),
  quote({ country: "DE", postcode: "18565", parcel: parcel(7.6, 40, 30, 20) }),
  quote({ country: "DE", postcode: "80331", parcel: parcel(9, 130, 30, 20) }),
  quote({ country: "AT", postcode: "6561", parcel: parcel(4.2, 30, 30, 30) }),
];
const bodies = quotes.map((q, i) => bookingRequest(q, `ORD-${1000 + i}`));
const cents = (amount: string) => Math.round(Number(amount) * 100);

test("a booking has exactly the fields the API accepts", () => {
  for (const body of bodies) {
    assert.deepEqual(Object.keys(body).sort(), BODY_FIELDS);
    assert.deepEqual(Object.keys(body.destination).sort(), ["country", "postcode"]);
  }
});

test("each charge has exactly a code, a label and an amount", () => {
  for (const body of bodies) {
    for (const charge of body.charges) {
      assert.deepEqual(Object.keys(charge).sort(), CHARGE_FIELDS);
      assert.ok(CHARGE_CODES.includes(charge.code), charge.code);
      assert.equal(typeof charge.label, "string");
    }
  }
});

test("amounts are net euros with exactly two decimals", () => {
  for (const [i, body] of bodies.entries()) {
    assert.match(body.total, AMOUNT);
    assert.equal(cents(body.total), quotes[i].totalCents);
    for (const charge of body.charges) {
      assert.match(charge.amount, AMOUNT);
    }
  }
});

test("the total is the sum of the charges", () => {
  for (const body of bodies) {
    const sum = body.charges.reduce((total, charge) => total + cents(charge.amount), 0);
    assert.equal(cents(body.total), sum);
  }
});

test("billable weight is sent in kg with one decimal", () => {
  assert.deepEqual(
    bodies.map((body) => body.billableWeightKg),
    ["2.5", "8.0", "16.0", "5.5"],
  );
});

test("service and currency are fixed values", () => {
  for (const body of bodies) {
    assert.equal(body.service, "parcel");
    assert.equal(body.currency, "EUR");
  }
});
