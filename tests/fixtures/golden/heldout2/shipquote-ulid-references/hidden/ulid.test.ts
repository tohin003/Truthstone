import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bookingRequest } from "../src/booking.ts";
import { quote } from "../src/quote.ts";

const BASE32 = "0123456789" + "ABCDEF" + "GHJKMN" + "PQRST" + "VWXYZ"; // no I, L, O or U
const ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/;
const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });

function timeOf(id: string): number {
  return [...id.slice(0, 10)].reduce((acc, ch) => acc * 32 + BASE32.indexOf(ch), 0);
}

test("a booking without a reference gets a ULID", () => {
  const before = Date.now();
  const { reference } = bookingRequest(q);
  const after = Date.now();
  assert.match(reference, ULID);
  const ms = timeOf(reference);
  assert.ok(before <= ms && ms <= after, `${ms} not in [${before}, ${after}]`);
});

test("generated references are unique and sort by creation time", () => {
  const seen = new Set<string>();
  for (let i = 0; i < 2000; i += 1) {
    seen.add(bookingRequest(q).reference);
  }
  assert.equal(seen.size, 2000);
  const first = bookingRequest(q).reference;
  const start = Date.now();
  while (Date.now() <= start + 2) {
    // let the clock move on by a few milliseconds
  }
  const second = bookingRequest(q).reference;
  assert.ok(first < second, `${first} !< ${second}`);
  const randomParts = new Set([...seen].map((id) => id.slice(10)));
  assert.equal(randomParts.size, 2000);
});

test("given references are used and checked as before", () => {
  assert.equal(bookingRequest(q, "ORD-1001").reference, "ORD-1001");
  assert.throws(() => bookingRequest(q, "ord 1001"), RangeError);
  assert.throws(() => bookingRequest(q, "AB"), RangeError);
});

test("no dependency was added", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.deepEqual(Object.keys(manifest.dependencies ?? {}), []);
  assert.deepEqual(Object.keys(manifest.devDependencies ?? {}), []);
});
