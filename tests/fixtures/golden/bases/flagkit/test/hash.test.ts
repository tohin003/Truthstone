import { test } from "node:test";
import assert from "node:assert/strict";
import { bucket, fnv1a32 } from "../src/hash.ts";

test("fnv1a32 matches the published FNV-1a test vectors", () => {
  assert.equal(fnv1a32(""), 0x811c9dc5);
  assert.equal(fnv1a32("a"), 0xe40c292c);
  assert.equal(fnv1a32("foobar"), 0xbf9cf968);
});

test("buckets match the values in the README (analytics depends on them)", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("new-checkout", "user-3"), 1);
  assert.equal(bucket("new-checkout", "alice"), 2);
  assert.equal(bucket("search-v2", "user-1"), 27);
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("offline-cart", "u-20001"), 0);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("buckets are 0-99 and depend on the flag as well as the user", () => {
  for (let i = 0; i < 500; i += 1) {
    const value = bucket("dark-mode", `user-${i}`);
    assert.ok(Number.isInteger(value) && value >= 0 && value < 100, `user-${i}: ${value}`);
  }
  assert.notEqual(bucket("new-checkout", "user-1"), bucket("search-v2", "user-1"));
});
