// Contract: the decisions the services rely on for the shipped configs, with no overrides and
// under the incident runbook's overrides (which only ever switch flags OFF). The incident
// dashboard counts `override:off` decisions, so every flag the runbook switches off must report
// exactly that. Run with `npm run test:contract`; CI runs it after `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { evaluate, loadConfig } from "../src/index.ts";
import type { Context, Env } from "../src/index.ts";

const load = (name: string) => loadConfig(fileURLToPath(new URL(`../flags/${name}.json`, import.meta.url)));
const storefront = load("storefront");
const mobile = load("mobile");

type Case = [flag: string, context: Context, env: Env, enabled: boolean, reason: string];

const STOREFRONT: Case[] = [
  ["new-checkout", { userId: "qa-anna" }, {}, true, "allowlist:hit"],
  ["new-checkout", { userId: "user-1", country: "AT" }, {}, true, "country:hit"],
  ["new-checkout", { userId: "user-3" }, {}, true, "percentage:1<20"],
  ["new-checkout", { userId: "user-1" }, {}, false, "no-match"],
  ["search-v2", { userId: "alice" }, {}, true, "percentage:6<10"],
  ["gift-cards", { userId: "qa-anna" }, {}, false, "disabled"],
  ["dark-mode", {}, {}, true, "everyone"],
  // the incident runbook: switch things off
  ["new-checkout", { userId: "qa-anna" }, { FLAGKIT_NEW_CHECKOUT: "off" }, false, "override:off"],
  ["search-v2", { userId: "alice" }, { FLAGKIT_SEARCH_V2: "OFF" }, false, "override:off"],
  ["gift-cards", { userId: "qa-anna" }, { FLAGKIT_GIFT_CARDS: "off" }, false, "override:off"],
  ["dark-mode", {}, { FLAGKIT_DARK_MODE: "off" }, false, "override:off"],
];

const MOBILE: Case[] = [
  ["one-tap-reorder", { plan: "plus" }, {}, true, "plan:hit"],
  ["one-tap-reorder", { userId: "u-20002", plan: "free" }, {}, true, "allowlist:hit"],
  ["offline-cart", { userId: "u-20001" }, {}, true, "percentage:0<50"],
  ["offline-cart", { userId: "u-77810" }, {}, false, "no-match"],
  ["offline-cart", { userId: "u-20001" }, { FLAGKIT_OFFLINE_CART: "off" }, false, "override:off"],
];

for (const [name, config, cases] of [["storefront", storefront, STOREFRONT], ["mobile", mobile, MOBILE]] as const) {
  test(`${name}: the decisions the services rely on`, () => {
    for (const [flag, context, env, enabled, reason] of cases) {
      const result = evaluate(config, flag, context, { env });
      assert.deepEqual([flag, result.enabled, result.reason], [flag, enabled, reason], JSON.stringify({ flag, context, env }));
    }
  });
}
