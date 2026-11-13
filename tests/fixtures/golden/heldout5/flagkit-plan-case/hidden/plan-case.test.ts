import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const flag = (key: string): Flag => ({ key, enabled: true, description: "", rules: [] });
const env = {};

test("a lower-case plan in the config matches the context's plan in any case", () => {
  const rule: Rule = { type: "plan", values: ["plus", "business"] };
  for (const plan of ["plus", "Plus", "PLUS", "Business", "bUsInEsS"]) {
    assert.deepEqual(MATCHERS.plan(rule, { plan }, flag("x")), { matched: true, reason: "plan:hit" }, plan);
  }
  assert.deepEqual(MATCHERS.plan(rule, { plan: "Free" }, flag("x")), { matched: false, reason: "plan:miss" });
  assert.deepEqual(MATCHERS.plan(rule, {}, flag("x")), { matched: false, reason: "plan:miss" });
});

test("a capitalised plan in the config matches too, in any case", () => {
  const config = parseConfig({
    flags: { "sso-login": { enabled: true, rules: [{ type: "plan", values: ["Enterprise", "Team"] }] } },
  });
  for (const plan of ["Enterprise", "enterprise", "ENTERPRISE", "team"]) {
    const result = evaluate(config, "sso-login", { plan }, { env });
    assert.equal(result.enabled, true, plan);
    assert.equal(result.reason, "plan:hit", plan);
  }
  assert.equal(evaluate(config, "sso-login", { plan: "plus" }, { env }).enabled, false);
});

test("evaluation through a parsed config", () => {
  const config = parseConfig({
    flags: {
      "one-tap-reorder": { enabled: true, rules: [{ type: "plan", values: ["plus", "business"] }] },
      "sso-login": { enabled: true, rules: [{ type: "plan", values: ["Enterprise"] }] },
    },
  });
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "Plus" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config, "sso-login", { plan: "Enterprise" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config, "sso-login", { plan: "enterprise" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config, "sso-login", { plan: "free" }, { env }).reason, "no-match");
});

test("the other matchers are unchanged", () => {
  assert.equal(MATCHERS.country({ type: "country", values: ["DE"] }, { country: "de" }, flag("x")).reason, "country:hit");
  assert.equal(MATCHERS.country({ type: "country", values: ["DE"] }, { country: "FR" }, flag("x")).reason, "country:miss");
  assert.equal(MATCHERS.allowlist({ type: "allowlist", values: ["qa-anna"] }, { userId: "qa-anna" }, flag("x")).reason, "allowlist:hit");
});
