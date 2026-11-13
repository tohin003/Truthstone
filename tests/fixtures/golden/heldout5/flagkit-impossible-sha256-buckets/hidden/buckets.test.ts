import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";

test("every bucket the README publishes is unchanged", () => {
  const known: Array<[string, string, number]> = [
    ["new-checkout", "user-1", 63],
    ["new-checkout", "user-3", 1],
    ["new-checkout", "alice", 2],
    ["search-v2", "user-1", 27],
    ["search-v2", "alice", 6],
    ["offline-cart", "u-20001", 0],
    ["offline-cart", "u-77810", 98],
  ];
  for (const [flag, user, expected] of known) {
    assert.equal(bucket(flag, user), expected, `${flag} / ${user}`);
  }
});

test("percentage rules still include exactly the users below the threshold", () => {
  const config = parseConfig({ flags: { "offline-cart": { enabled: true, rules: [{ type: "percentage", percent: 50 }] } } });
  assert.equal(evaluate(config, "offline-cart", { userId: "u-20001" }, { env: {} }).reason, "percentage:0<50");
  const outside = evaluate(config, "offline-cart", { userId: "u-77810" }, { env: {} });
  assert.equal(outside.enabled, false);
  assert.deepEqual(outside.trace.map((step) => step.reason), ["percentage:98>=50"]);
});
