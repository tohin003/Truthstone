import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { evaluate, loadConfig, parseConfig } from "../src/index.ts";

const load = (name: string) => loadConfig(fileURLToPath(new URL(`../flags/${name}.json`, import.meta.url)));

const config = parseConfig({
  flags: {
    killed: { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    live: { enabled: true, rules: [{ type: "country", values: ["DE"] }] },
    plain: { enabled: true },
  },
});

test("an on override cannot turn on a disabled flag", () => {
  assert.deepEqual(evaluate(config, "killed", { country: "DE" }, { env: { FLAGKIT_KILLED: "on" } }), { flag: "killed", enabled: false, reason: "disabled", trace: [] });
  assert.equal(evaluate(config, "live", { country: "FR" }, { env: { FLAGKIT_LIVE: "on" } }).reason, "override:on");
  assert.equal(evaluate(config, "plain", {}, { env: { FLAGKIT_PLAIN: " On " } }).reason, "override:on");
});

test("off overrides work as before, on every flag", () => {
  for (const flag of ["killed", "live", "plain"]) {
    const env = { [`FLAGKIT_${flag.toUpperCase()}`]: "off" };
    assert.deepEqual(evaluate(config, flag, { country: "DE" }, { env }), { flag, enabled: false, reason: "override:off", trace: [] });
  }
  assert.equal(evaluate(config, "nope", {}, { env: { FLAGKIT_NOPE: "off" } }).reason, "unknown-flag");
});

test("the shipped configs keep their runbook decisions", () => {
  const storefront = load("storefront");
  assert.equal(evaluate(storefront, "gift-cards", { userId: "qa-anna" }, { env: { FLAGKIT_GIFT_CARDS: "off" } }).reason, "override:off");
  assert.equal(evaluate(storefront, "gift-cards", { userId: "qa-anna" }, { env: { FLAGKIT_GIFT_CARDS: "on" } }).reason, "disabled");
  assert.equal(evaluate(storefront, "new-checkout", { userId: "user-3" }, { env: {} }).reason, "percentage:1<20");
  assert.equal(evaluate(load("mobile"), "offline-cart", { userId: "u-20001" }, { env: { FLAGKIT_OFFLINE_CART: "off" } }).reason, "override:off");
});
