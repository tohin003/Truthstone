// Requirement one and the README's evaluation order: an env override wins, even over "enabled": false.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "gift-cards": { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    "offline-cart": { enabled: false },
    "dark-mode": { enabled: true },
  },
});

test("FLAGKIT_<KEY>=on forces a disabled flag on", () => {
  assert.deepEqual(evaluate(config, "gift-cards", { country: "FR" }, { env: { FLAGKIT_GIFT_CARDS: "on" } }), {
    flag: "gift-cards",
    enabled: true,
    reason: "override:on",
    trace: [],
  });
  assert.equal(evaluate(config, "offline-cart", {}, { env: { FLAGKIT_OFFLINE_CART: " ON " } }).enabled, true);
});

test("off overrides, the kill switch without an override, and unknown flags are unchanged", () => {
  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_DARK_MODE: "off" } }).reason, "override:off");
  assert.equal(evaluate(config, "gift-cards", { country: "DE" }, { env: {} }).reason, "disabled");
  assert.equal(evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "off" } }).enabled, false);
  assert.equal(evaluate(config, "nope", {}, { env: { FLAGKIT_NOPE: "on" } }).reason, "unknown-flag");
});

test("the CLI forces a disabled flag on from the environment", () => {
  const configPath = fileURLToPath(new URL("../test/fixtures/flags.json", import.meta.url));
  let stdout = "";
  const status = main(["eval", configPath, "gift-cards"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: () => true },
    env: { FLAGKIT_GIFT_CARDS: "on" },
  });
  assert.equal(status, 0);
  assert.equal(stdout, "on (override:on)\n");
});
