// Hidden checks: country rules match the context's country in any case, as the README's rule table says.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const flag = (key: string): Flag => ({ key, enabled: true, description: "", rules: [] });
const rule: Rule = { type: "country", values: ["DE", "AT", "CH"] };

test("the country matcher ignores the case of the context's country", () => {
  for (const country of ["DE", "de", "De", "dE", "at", "Ch"]) {
    assert.deepEqual(MATCHERS.country(rule, { country }, flag("x")), { matched: true, reason: "country:hit" }, country);
  }
  for (const country of ["FR", "fr", "us"]) {
    assert.deepEqual(MATCHERS.country(rule, { country }, flag("x")), { matched: false, reason: "country:miss" }, country);
  }
  assert.deepEqual(MATCHERS.country(rule, {}, flag("x")), { matched: false, reason: "country:miss" });
});

test("evaluation turns a country-targeted flag on for a lower-case country", () => {
  const config = parseConfig({ flags: { "new-checkout": { enabled: true, rules: [{ type: "country", values: ["DE", "AT"] }] } } });
  assert.equal(evaluate(config, "new-checkout", { country: "de" }, { env: {} }).reason, "country:hit");
  assert.equal(evaluate(config, "new-checkout", { country: "AT" }, { env: {} }).enabled, true);
  assert.equal(evaluate(config, "new-checkout", { country: "fr" }, { env: {} }).reason, "no-match");
});

test("the other matchers are unchanged", () => {
  assert.equal(MATCHERS.plan({ type: "plan", values: ["plus"] }, { plan: "plus" }, flag("x")).reason, "plan:hit");
  assert.equal(MATCHERS.allowlist({ type: "allowlist", values: ["qa-anna"] }, { userId: "qa-ben" }, flag("x")).reason, "allowlist:miss");
  assert.deepEqual(MATCHERS.percentage({ type: "percentage", percent: 10 }, { userId: "alice" }, flag("search-v2")), {
    matched: true,
    reason: "percentage:6<10",
  });
});
