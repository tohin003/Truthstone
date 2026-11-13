// Hidden checks: buckets and percentage rules keep their documented meaning, and nobody who has search-v2 today loses it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";

// The README's formula, written out independently: fnv1a32("<flag key>:<user id>") % 100.
function referenceBucket(flagKey: string, userId: string): number {
  const text = `${flagKey}:${userId}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return (hash >>> 0) % 100;
}

const USERS = [
  ...Array.from({ length: 1500 }, (_, i) => `user-${i}`),
  ...Array.from({ length: 1500 }, (_, i) => `u-${10000 + i}`),
  "alice",
  "qa-anna",
  "qa-ben",
];

const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("the README's known buckets are unchanged", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("new-checkout", "user-3"), 1);
  assert.equal(bucket("new-checkout", "alice"), 2);
  assert.equal(bucket("search-v2", "user-1"), 27);
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("offline-cart", "u-20001"), 0);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("no existing user's bucket changes, for any flag", () => {
  for (const flag of ["search-v2", "new-checkout", "offline-cart"]) {
    for (const user of USERS.slice(0, 600)) {
      assert.equal(bucket(flag, user), referenceBucket(flag, user), `${flag} ${user}`);
    }
  }
});

test("a percentage rule of N turns a flag on for exactly the users whose bucket is below N", () => {
  for (const percent of [5, 10, 20]) {
    const config = parseConfig({ flags: { "search-v2": { enabled: true, rules: [{ type: "percentage", percent }] } } });
    for (const user of USERS.slice(0, 800)) {
      const result = evaluate(config, "search-v2", { userId: user }, { env: {} });
      assert.equal(result.enabled, referenceBucket("search-v2", user) < percent, `${percent}% ${user}`);
    }
  }
});

test("everyone who has search-v2 today (bucket below 10) still has it", () => {
  const config = loadConfig(storefront);
  const today = USERS.filter((user) => referenceBucket("search-v2", user) < 10);
  assert.ok(today.length > 100);
  for (const user of today) {
    assert.equal(evaluate(config, "search-v2", { userId: user }, { env: {} }).enabled, true, user);
  }
});

test("the other storefront flags are untouched", () => {
  const config = loadConfig(storefront);
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "DE" }, { env: {} }).reason, "country:hit");
  assert.equal(evaluate(config, "gift-cards", { userId: "alice" }, { env: {} }).reason, "disabled");
  assert.equal(evaluate(config, "dark-mode", { userId: "alice" }, { env: {} }).reason, "everyone");
});
