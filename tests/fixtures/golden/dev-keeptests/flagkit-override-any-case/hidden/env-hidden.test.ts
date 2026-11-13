import { test } from "node:test";
import assert from "node:assert/strict";
import { activeOverrides, envOverride } from "../src/env.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] },
    "gift-cards": { enabled: false },
  },
});

for (const [value, forced] of [
  ["on", true], ["ON", true], ["On", true], ["  oN\t", true],
  ["off", false], ["OFF", false], [" Off ", false], ["oFf", false],
] as const) {
  test(`override value ${JSON.stringify(value)} forces the flag ${forced ? "on" : "off"}`, () => {
    assert.equal(envOverride("new-checkout", { FLAGKIT_NEW_CHECKOUT: value }), forced);
  });
}

test("other values are still ignored, in any case", () => {
  for (const value of ["", "yes", "TRUE", "1", "0", "ofF!", "o n", "enabled"]) {
    assert.equal(envOverride("new-checkout", { FLAGKIT_NEW_CHECKOUT: value }), undefined, value);
  }
});

test("an upper-case override decides the evaluation", () => {
  assert.deepEqual(
    evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "ON" } }),
    { flag: "gift-cards", enabled: true, reason: "override:on", trace: [] },
  );
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: { FLAGKIT_NEW_CHECKOUT: " OFF " } }).reason, "override:off");
});

test("activeOverrides reads values in any case", () => {
  const env = { FLAGKIT_NEW_CHECKOUT: "Off", FLAGKIT_GIFT_CARDS: "ON" };
  assert.deepEqual([...activeOverrides(["new-checkout", "gift-cards"], env)], [["new-checkout", false], ["gift-cards", true]]);
});
