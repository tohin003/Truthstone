import { test } from "node:test";
import assert from "node:assert/strict";
import { formatAmount, formatEUR } from "../src/money.ts";
import { quote } from "../src/quote.ts";

test("formatEUR groups thousands with commas", () => {
  assert.equal(formatEUR(123456), "€1,234.56");
  assert.equal(formatEUR(100000), "€1,000.00");
  assert.equal(formatEUR(100000000), "€1,000,000.00");
  assert.equal(formatEUR(1234567890), "€12,345,678.90");
});

test("formatEUR groups negative amounts too", () => {
  assert.equal(formatEUR(-150000), "-€1,500.00");
  assert.equal(formatEUR(-150), "-€1.50");
});

test("amounts under a thousand euros are unchanged", () => {
  assert.equal(formatEUR(99999), "€999.99");
  assert.equal(formatEUR(749), "€7.49");
  assert.equal(formatEUR(5), "€0.05");
  assert.equal(formatEUR(0), "€0.00");
});

test("formatAmount, the machine-readable form, is not grouped", () => {
  assert.equal(formatAmount(123456), "1234.56");
  assert.equal(formatAmount(100000000), "1000000.00");
  assert.equal(formatAmount(-150000), "-1500.00");
});

test("the README's oversize surcharge still applies to Austria (#73 is undecided)", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } });
  assert.equal(q.lines.find((line) => line.code === "oversize")?.amountCents, 1200);
});
