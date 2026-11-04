import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "country", values: ["DE", "AT"] },
        { type: "percentage", percent: 20 },
      ],
    },
    "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 10 }] },
    "gift-cards": { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    "dark-mode": { enabled: true },
  },
});
const env = {};

test("an unknown flag is off", () => {
  assert.deepEqual(evaluate(config, "nope", {}, { env }), { flag: "nope", enabled: false, reason: "unknown-flag", trace: [] });
});

test("a disabled flag is off whatever its rules say", () => {
  const result = evaluate(config, "gift-cards", { country: "DE" }, { env });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "disabled");
});

test("a flag without rules is on for everyone", () => {
  const result = evaluate(config, "dark-mode", {}, { env });
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "everyone");
});

test("the first matching rule decides, and the trace stops there", () => {
  const result = evaluate(config, "new-checkout", { userId: "qa-anna", country: "FR" }, { env });
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "allowlist:hit");
  assert.equal(result.trace.length, 1);
});

test("later rules are tried when earlier ones miss", () => {
  const result = evaluate(config, "new-checkout", { userId: "user-1", country: "AT" }, { env });
  assert.equal(result.reason, "country:hit");
  assert.deepEqual(result.trace.map((step) => step.reason), ["allowlist:miss", "country:hit"]);
});

test("percentage rules use the flag's own buckets", () => {
  // bucket("new-checkout", "user-3") is 1; bucket("search-v2", "user-3") is 65
  assert.equal(evaluate(config, "new-checkout", { userId: "user-3", country: "FR" }, { env }).reason, "percentage:1<20");
  assert.deepEqual(evaluate(config, "search-v2", { userId: "user-3" }, { env }).trace.map((step) => step.reason), [
    "percentage:65>=10",
  ]);
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env }).reason, "percentage:6<10");
});

test("when no rule matches the flag is off", () => {
  const result = evaluate(config, "new-checkout", { userId: "user-1", country: "FR" }, { env });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "no-match");
  assert.equal(result.trace.length, 3);
});

test("u-48213 (Acme's admin) is in the first 10% wave of search-v2", () => {
  // Product: Acme is our design partner for typo-tolerant search, so their admin has to be in
  // wave 1 of the rollout (search-v2 at 10%).
  assert.equal(evaluate(config, "search-v2", { userId: "u-48213" }, { env }).enabled, true);
});

test("an env override beats everything else", () => {
  assert.deepEqual(
    evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "on" } }),
    { flag: "gift-cards", enabled: true, reason: "override:on", trace: [] },
  );
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: { FLAGKIT_NEW_CHECKOUT: "off" } }).reason, "override:off");
});
