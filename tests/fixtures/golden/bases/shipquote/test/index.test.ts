import { test } from "node:test";
import assert from "node:assert/strict";
import * as shipquote from "../src/index.ts";

test("the public API exports the quoting functions", () => {
  for (const name of ["quote", "bookingRequest", "zoneFor", "billableWeight", "deliveryDate", "rateCard", "formatEUR"]) {
    assert.equal(typeof (shipquote as Record<string, unknown>)[name], "function", name);
  }
  assert.equal(shipquote.DEFAULT_YEAR, 2026);
});

test("a quote through the public API", () => {
  const q = shipquote.quote({
    country: "DE",
    postcode: "10115",
    parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 },
  });
  assert.equal(shipquote.formatEUR(q.totalCents), "€7.49");
});
