import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { quote, type QuoteRequest } from "../src/quote.ts";

// The checkout's contract for every quote (see the README, "The quote contract").
const schema = JSON.parse(readFileSync(new URL("../schema/quote.schema.json", import.meta.url), "utf8"));
const line = schema.$defs.line;

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({ weightKg, lengthCm, widthCm, heightCm });
const SAMPLES: QuoteRequest[] = [
  { country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) },
  { country: "DE", postcode: "18565", parcel: box(1, 20, 15, 10), shipDate: "2026-11-05" },
  { country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) },
  { country: "AT", postcode: "6561", parcel: box(4.2, 30, 30, 30), shipDate: "2026-12-23" },
];

test("every quote matches the checkout's schema", () => {
  for (const request of SAMPLES) {
    const q = JSON.parse(JSON.stringify(quote(request)));
    for (const key of Object.keys(q)) {
      assert.ok(key in schema.properties, `unexpected field ${key}`);
    }
    for (const key of schema.required) {
      assert.ok(key in q, `missing ${key}`);
    }
    assert.ok(schema.properties.country.enum.includes(q.country));
    assert.equal(q.billableKg % schema.properties.billableKg.multipleOf, 0);
    for (const charge of q.lines) {
      assert.deepEqual(Object.keys(charge).sort(), [...line.required].sort());
      assert.ok(line.properties.code.enum.includes(charge.code), charge.code);
      assert.ok(Number.isInteger(charge.amountCents) && charge.amountCents >= line.properties.amountCents.minimum, charge.code);
    }
    assert.equal(q.totalCents, q.lines.reduce((sum: number, charge: { amountCents: number }) => sum + charge.amountCents, 0));
  }
});
