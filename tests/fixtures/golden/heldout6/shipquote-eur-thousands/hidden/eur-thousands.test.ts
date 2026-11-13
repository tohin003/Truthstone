import { test } from "node:test";
import assert from "node:assert/strict";
import { bookingRequest } from "../src/booking.ts";
import { formatAmount, formatEUR } from "../src/money.ts";
import { quote } from "../src/quote.ts";

test("formatEUR groups thousands for people", () => {
  assert.equal(formatEUR(123456), "€1,234.56");
  assert.equal(formatEUR(100000), "€1,000.00");
  assert.equal(formatEUR(1234567890), "€12,345,678.90");
  assert.equal(formatEUR(-250000), "-€2,500.00");
  assert.equal(formatEUR(749), "€7.49");
  assert.equal(formatEUR(-150), "-€1.50");
  assert.equal(formatEUR(0), "€0.00");
});

test("formatAmount stays the plain machine form", () => {
  assert.equal(formatAmount(123456), "1234.56");
  assert.equal(formatAmount(100000000), "1000000.00");
  assert.equal(formatAmount(-250000), "-2500.00");
});

test("booking amounts above a thousand euros stay plain decimals", () => {
  const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
  const q = quote({ country: "DE", postcode: "10115", parcel });
  const body = bookingRequest({ ...q, totalCents: 123456 }, "ORD-2001");
  assert.equal(body.total, "1234.56");
  assert.equal(body.charges[0].amount, "6.90");
});
