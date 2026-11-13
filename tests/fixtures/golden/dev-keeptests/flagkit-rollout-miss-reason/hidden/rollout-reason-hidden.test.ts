import { test } from "node:test";
import assert from "node:assert/strict";
import { explain } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";
import { MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const flag = (key: string): Flag => ({ key, enabled: true, description: "", rules: [] });
const rollout = (percent: number): Rule => ({ type: "percentage", percent });

test("a user outside the rollout gets bucket>=percent", () => {
  // bucket("new-checkout", "user-1") is 63; bucket("offline-cart", "u-77810") is 98
  assert.deepEqual(MATCHERS.percentage(rollout(20), { userId: "user-1" }, flag("new-checkout")), { matched: false, reason: "percentage:63>=20" });
  assert.deepEqual(MATCHERS.percentage(rollout(50), { userId: "u-77810" }, flag("offline-cart")), { matched: false, reason: "percentage:98>=50" });
  assert.deepEqual(MATCHERS.percentage(rollout(0), { userId: "u-20001" }, flag("offline-cart")), { matched: false, reason: "percentage:0>=0" });
});

test("a bucket equal to the percentage is outside, and says so", () => {
  for (const user of ["user-1", "user-3", "alice", "u-1", "u-2", "u-3"]) {
    const own = bucket("search-v2", user);
    assert.deepEqual(MATCHERS.percentage(rollout(own), { userId: user }, flag("search-v2")), { matched: false, reason: `percentage:${own}>=${own}` });
  }
});

test("hits, users without an id and the other matchers keep their reasons", () => {
  assert.deepEqual(MATCHERS.percentage(rollout(20), { userId: "alice" }, flag("new-checkout")), { matched: true, reason: "percentage:2<20" });
  assert.deepEqual(MATCHERS.percentage(rollout(100), {}, flag("new-checkout")), { matched: false, reason: "percentage:no-user" });
  assert.equal(MATCHERS.country({ type: "country", values: ["DE"] }, { country: "fr" }, flag("x")).reason, "country:miss");
  assert.equal(MATCHERS.plan({ type: "plan", values: ["plus"] }, { plan: "plus" }, flag("x")).reason, "plan:hit");
  assert.equal(MATCHERS.allowlist({ type: "allowlist", values: ["qa-anna"] }, { userId: "qa-ben" }, flag("x")).reason, "allowlist:miss");
});

test("buckets are unchanged for existing users", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("new-checkout", "user-3"), 1);
  assert.equal(bucket("search-v2", "user-1"), 27);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("explain shows the miss reason of a rollout the user is outside", () => {
  const config = parseConfig({ flags: { "new-checkout": { enabled: true, rules: [{ type: "percentage", percent: 20 }] } } });
  const result = evaluate(config, "new-checkout", { userId: "user-1" }, { env: {} });
  assert.equal(result.reason, "no-match");
  assert.match(explain(config.flags.get("new-checkout")!, result), /miss\s+percentage:63>=20/);
});
