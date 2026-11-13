// The documented evaluation order (README "Evaluation", evaluate.ts): unknown flag, then the
// environment override, then the kill switch, then rules.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "gift-cards": { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    "promo-banner": { enabled: false },
    "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] },
  },
});

test("an environment override turns a disabled flag on", () => {
  for (const flag of ["gift-cards", "promo-banner"]) {
    const name = flag === "gift-cards" ? "FLAGKIT_GIFT_CARDS" : "FLAGKIT_PROMO_BANNER";
    const result = evaluate(config, flag, {}, { env: { [name]: "on" } });
    assert.equal(result.enabled, true, flag);
    assert.equal(result.reason, "override:on", flag);
  }
});

test("an environment override turns a matching flag off", () => {
  const result = evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: { FLAGKIT_NEW_CHECKOUT: "off" } });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "override:off");
});

test("without an override a disabled flag is off and rules decide the rest", () => {
  assert.equal(evaluate(config, "gift-cards", { country: "DE" }, { env: {} }).reason, "disabled");
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "nope", {}, { env: { FLAGKIT_NOPE: "on" } }).reason, "unknown-flag");
});
