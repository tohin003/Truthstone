import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

// Incident review, 2026-11-10: a stale FLAGKIT_GIFT_CARDS=on on two web hosts kept gift cards
// on for an hour after ops had disabled the flag. The kill switch has to be final.
const config = parseConfig({
  flags: {
    "gift-cards": { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] },
  },
});

test("the kill switch wins: a disabled flag stays off even when the environment says on", () => {
  assert.deepEqual(
    evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "on" } }),
    { flag: "gift-cards", enabled: false, reason: "disabled", trace: [] },
  );
});

test("overrides still switch enabled flags", () => {
  const result = evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: { FLAGKIT_NEW_CHECKOUT: "off" } });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "override:off");
});
