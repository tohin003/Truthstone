import { test } from "node:test";
import assert from "node:assert/strict";
import { matcherFor, MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const flag = (key: string, rules: Rule[] = []): Flag => ({ key, enabled: true, description: "", rules });

test("country rules match the context's country, in any case", () => {
  const rule: Rule = { type: "country", values: ["DE", "AT"] };
  assert.deepEqual(MATCHERS.country(rule, { country: "DE" }, flag("x")), { matched: true, reason: "country:hit" });
  assert.deepEqual(MATCHERS.country(rule, { country: "at" }, flag("x")), { matched: true, reason: "country:hit" });
  assert.deepEqual(MATCHERS.country(rule, { country: "FR" }, flag("x")), { matched: false, reason: "country:miss" });
  assert.deepEqual(MATCHERS.country(rule, {}, flag("x")), { matched: false, reason: "country:miss" });
});

test("plan rules match the context's plan", () => {
  const rule: Rule = { type: "plan", values: ["plus", "business"] };
  assert.equal(MATCHERS.plan(rule, { plan: "plus" }, flag("x")).reason, "plan:hit");
  assert.equal(MATCHERS.plan(rule, { plan: "free" }, flag("x")).reason, "plan:miss");
});

test("plan rules match in any case", () => {
  // the mobile app sends the plan's display name, e.g. "Plus"
  const rule: Rule = { type: "plan", values: ["plus", "business"] };
  assert.deepEqual(MATCHERS.plan(rule, { plan: "Plus" }, flag("x")), { matched: true, reason: "plan:hit" });
  assert.deepEqual(MATCHERS.plan(rule, { plan: "BUSINESS" }, flag("x")), { matched: true, reason: "plan:hit" });
  assert.deepEqual(MATCHERS.plan(rule, { plan: "Free" }, flag("x")), { matched: false, reason: "plan:miss" });
});

test("allowlist rules match listed user ids only", () => {
  const rule: Rule = { type: "allowlist", values: ["qa-anna", "qa-ben"] };
  assert.deepEqual(MATCHERS.allowlist(rule, { userId: "qa-ben" }, flag("x")), { matched: true, reason: "allowlist:hit" });
  assert.deepEqual(MATCHERS.allowlist(rule, { userId: "qa-carl" }, flag("x")), { matched: false, reason: "allowlist:miss" });
  assert.deepEqual(MATCHERS.allowlist(rule, {}, flag("x")), { matched: false, reason: "allowlist:miss" });
});

test("percentage rules include users whose bucket is below the percentage", () => {
  const rule: Rule = { type: "percentage", percent: 10 };
  // bucket("search-v2", "alice") is 6, bucket("search-v2", "user-1") is 27
  assert.deepEqual(MATCHERS.percentage(rule, { userId: "alice" }, flag("search-v2")), { matched: true, reason: "percentage:6<10" });
  assert.deepEqual(MATCHERS.percentage(rule, { userId: "user-1" }, flag("search-v2")), { matched: false, reason: "percentage:27>=10" });
});

test("percentage rules at 0 and 100, and without a user", () => {
  const none: Rule = { type: "percentage", percent: 0 };
  const all: Rule = { type: "percentage", percent: 100 };
  assert.equal(MATCHERS.percentage(none, { userId: "user-3" }, flag("new-checkout")).matched, false);
  assert.equal(MATCHERS.percentage(all, { userId: "u-77810" }, flag("offline-cart")).matched, true);
  assert.deepEqual(MATCHERS.percentage(all, {}, flag("offline-cart")), { matched: false, reason: "percentage:no-user" });
});

test("matcherFor finds registered matchers and refuses others", () => {
  assert.equal(matcherFor("plan"), MATCHERS.plan);
  assert.throws(() => matcherFor("weekday"), /no matcher for rule type "weekday"/);
  assert.throws(() => matcherFor("toString"), /no matcher/);
});
