import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync } from "node:fs";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };

function dumps(): string[] {
  const dir = new URL("../tmp/quote-dumps/", import.meta.url);
  return existsSync(dir) ? readdirSync(dir) : [];
}

test("quotes no longer write dumps, even with SHIPQUOTE_DUMP set", () => {
  process.env.SHIPQUOTE_DUMP = "1";
  try {
    const q = quote({ country: "DE", postcode: "10115", parcel });
    assert.equal(q.totalCents, 749);
  } finally {
    delete process.env.SHIPQUOTE_DUMP;
  }
  assert.deepEqual(dumps(), []);
});

test("quotes are unchanged", () => {
  const q = quote({ country: "DE", postcode: "25980", parcel, shipDate: "2026-11-05" });
  assert.deepEqual(
    q.lines.map((line) => [line.code, line.amountCents]),
    [["base", 690], ["fuel", 59], ["remote", 450]],
  );
  assert.equal(q.totalCents, 1199);
  assert.equal(q.deliveryDate, "2026-11-06");
});
