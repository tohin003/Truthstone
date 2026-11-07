import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const FLAGS = fileURLToPath(new URL("../flags/", import.meta.url));
const env = {};

function rejects(rules: unknown[], ...patterns: RegExp[]) {
  assert.throws(
    () => parseConfig({ flags: { "promo-banner": { enabled: true, rules } } }),
    (error: unknown) => error instanceof ConfigError && patterns.every((pattern) => pattern.test(error.message)),
    JSON.stringify(rules),
  );
}

test("a duplicated value is a config error naming the flag, the rule and the value", () => {
  rejects([{ type: "allowlist", values: ["qa-anna", "qa-ben", "qa-anna"] }], /flag "promo-banner"/, /rule 1\b/, /qa-anna/);
  rejects(
    [{ type: "plan", values: ["plus"] }, { type: "country", values: ["DE", "AT", "DE"] }],
    /flag "promo-banner"/,
    /rule 2\b/,
    /DE/,
  );
  rejects(
    [{ type: "country", values: ["DE"] }, { type: "percentage", percent: 10 }, { type: "plan", values: ["business", "business"] }],
    /flag "promo-banner"/,
    /rule 3\b/,
    /business/,
  );
});

test("lists without duplicates are still valid", () => {
  const config = parseConfig({
    flags: {
      "promo-banner": {
        enabled: true,
        rules: [
          { type: "allowlist", values: ["qa-anna", "qa-ben"] },
          { type: "country", values: ["DE", "AT", "CH"] },
          { type: "plan", values: ["plus"] },
          { type: "percentage", percent: 10 },
        ],
      },
      "other-flag": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] },
    },
  });
  assert.equal(config.flags.get("promo-banner")?.rules.length, 4);
  assert.equal(evaluate(config, "other-flag", { userId: "qa-anna" }, { env }).reason, "allowlist:hit");
});

test("the other validation errors are unchanged", () => {
  rejects([{ type: "allowlist", values: [] }], /flag "promo-banner": rule 1: "values" must be/);
  rejects([{ type: "country", values: ["de"] }], /rule 1: "values" must be/);
  rejects([{ type: "weekday" }], /rule 1: unknown rule type "weekday"/);
});

test("every production config in flags/ still loads", () => {
  const names = readdirSync(FLAGS).filter((file) => file.endsWith(".json")).sort();
  assert.ok(names.includes("mobile.json") && names.includes("storefront.json"), names.join(", "));
  for (const name of names) {
    assert.doesNotThrow(() => loadConfig(`${FLAGS}${name}`), name);
  }
});

test("the production configs still decide as before", () => {
  const mobile = loadConfig(`${FLAGS}mobile.json`);
  for (const userId of ["u-20001", "u-20002", "u-31877"]) {
    assert.equal(evaluate(mobile, "one-tap-reorder", { userId }, { env }).reason, "allowlist:hit", userId);
  }
  assert.equal(evaluate(mobile, "one-tap-reorder", { userId: "u-1", plan: "business" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(mobile, "one-tap-reorder", { userId: "u-1", plan: "free" }, { env }).reason, "no-match");
  assert.equal(evaluate(mobile, "offline-cart", { userId: "u-20001" }, { env }).reason, "percentage:0<50");
  const storefront = loadConfig(`${FLAGS}storefront.json`);
  assert.equal(evaluate(storefront, "new-checkout", { userId: "u-10234" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(storefront, "new-checkout", { userId: "user-1", country: "CH" }, { env }).reason, "country:hit");
  assert.equal(evaluate(storefront, "dark-mode", {}, { env }).reason, "everyone");
});
