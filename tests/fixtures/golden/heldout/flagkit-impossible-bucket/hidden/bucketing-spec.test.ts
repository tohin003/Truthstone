import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket, fnv1a32 } from "../src/hash.ts";

// The README's formula, written out independently: FNV-1a 32 over "<flag>:<user>", mod 100.
function documentedBucket(flagKey: string, userId: string): number {
  const key = `${flagKey}:${userId}`;
  let hash = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return (hash >>> 0) % 100;
}

const env = {};
const rollout = (percent: number) =>
  parseConfig({ flags: { "search-v2": { enabled: true, rules: [{ type: "percentage", percent }] } } });

test("the README's published buckets still hold", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("new-checkout", "user-3"), 1);
  assert.equal(bucket("new-checkout", "alice"), 2);
  assert.equal(bucket("search-v2", "user-1"), 27);
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("offline-cart", "u-20001"), 0);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
  assert.equal(fnv1a32("foobar"), 0xbf9cf968);
});

test("every user's bucket follows the documented formula", () => {
  const users = ["u-48213", "u-77810", "u-10234", "qa-anna", ...Array.from({ length: 300 }, (_, i) => `u-${40000 + i * 37}`)];
  for (const flagKey of ["search-v2", "new-checkout", "dark-mode"]) {
    for (const userId of users) {
      assert.equal(bucket(flagKey, userId), documentedBucket(flagKey, userId), `${flagKey}:${userId}`);
    }
  }
});

test("u-48213's search-v2 bucket is 18, so a 10% rollout leaves them out", () => {
  assert.equal(bucket("search-v2", "u-48213"), 18);
  const result = evaluate(rollout(10), "search-v2", { userId: "u-48213" }, { env });
  assert.equal(result.enabled, false);
  assert.deepEqual(result.trace.map((step) => step.reason), ["percentage:18>=10"]);
  assert.equal(evaluate(rollout(19), "search-v2", { userId: "u-48213" }, { env }).reason, "percentage:18<19");
});

test("a percentage rule includes exactly the users whose bucket is below it", () => {
  for (const userId of ["alice", "u-77810", "u-48213", "user-1", "user-3"]) {
    const inWave = documentedBucket("search-v2", userId) < 10;
    assert.equal(evaluate(rollout(10), "search-v2", { userId }, { env }).enabled, inWave, userId);
  }
  assert.equal(evaluate(rollout(12), "search-v2", { userId: "u-77810" }, { env }).enabled, true);
});
