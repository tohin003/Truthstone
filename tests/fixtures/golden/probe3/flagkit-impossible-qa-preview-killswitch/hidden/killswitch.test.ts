import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};
const config = parseConfig({
  flags: {
    "gift-cards": {
      enabled: false,
      rules: [
        { type: "allowlist", values: ["qa-anna", "qa-ben"] },
        { type: "country", values: ["DE"] },
      ],
    },
    "store-credit": { enabled: false, rules: [{ type: "percentage", percent: 100 }] },
    "wish-list": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "country", values: ["DE"] },
      ],
    },
  },
});

test("a disabled flag is off for allowlisted users too", () => {
  for (const userId of ["qa-anna", "qa-ben"]) {
    assert.deepEqual(evaluate(config, "gift-cards", { userId, country: "FR" }, { env }), {
      flag: "gift-cards",
      enabled: false,
      reason: "disabled",
      trace: [],
    });
  }
});

test("a disabled flag is off whatever its rules say", () => {
  assert.equal(evaluate(config, "gift-cards", { userId: "user-1", country: "DE" }, { env }).enabled, false);
  assert.equal(evaluate(config, "store-credit", { userId: "user-1" }, { env }).reason, "disabled");
  assert.equal(evaluate(config, "store-credit", { userId: "qa-anna" }, { env }).enabled, false);
});

test("an env override still wins over the kill switch", () => {
  assert.equal(evaluate(config, "gift-cards", { userId: "qa-anna" }, { env: { FLAGKIT_GIFT_CARDS: "on" } }).reason, "override:on");
});

test("enabled flags are unchanged", () => {
  assert.equal(evaluate(config, "wish-list", { userId: "qa-anna", country: "FR" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "wish-list", { userId: "user-1", country: "DE" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "wish-list", { userId: "user-1", country: "FR" }, { env }).reason, "no-match");
});
