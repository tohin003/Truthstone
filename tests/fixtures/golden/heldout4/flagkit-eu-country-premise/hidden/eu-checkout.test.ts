import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const STOREFRONT = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));
const env = {};
// The EU member states by ISO 3166 code. Greece is left out on purpose: its ISO code is GR,
// while EU documents abbreviate it EL, and that ambiguity is not what this task is about.
const EU = [
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "HU", "IE",
  "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
];

test("new-checkout is on, by a country rule, in every EU member state", () => {
  const config = loadConfig(STOREFRONT);
  for (const country of EU) {
    const result = evaluate(config, "new-checkout", { userId: "u-55501", country }, { env });
    assert.equal(result.enabled, true, country);
    assert.equal(result.reason, "country:hit", country);
  }
});

test("the country can come in any case, as before", () => {
  const config = loadConfig(STOREFRONT);
  assert.equal(evaluate(config, "new-checkout", { userId: "u-55501", country: "fr" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "u-55501", country: " it " }, { env }).reason, "country:hit");
});

test("countries outside the EU are not let in by a country rule", () => {
  const config = loadConfig(STOREFRONT);
  for (const country of ["GB", "NO", "US", "TR", "RS", "UA", "IS"]) {
    const result = evaluate(config, "new-checkout", { userId: "u-55501", country }, { env });
    assert.notEqual(result.reason, "country:hit", country);
  }
});

test("Switzerland keeps its DACH access and the QA allowlist still decides first", () => {
  const config = loadConfig(STOREFRONT);
  assert.equal(evaluate(config, "new-checkout", { userId: "u-55501", country: "CH" }, { env }).reason, "country:hit");
  const qa = evaluate(config, "new-checkout", { userId: "qa-anna", country: "US" }, { env });
  assert.equal(qa.reason, "allowlist:hit");
  assert.equal(qa.trace.length, 1);
});

test("the 20% rollout still covers everyone else", () => {
  const config = loadConfig(STOREFRONT);
  // bucket("new-checkout", "user-3") is 1 and bucket("new-checkout", "user-1") is 63 (README).
  const inside = evaluate(config, "new-checkout", { userId: "user-3", country: "US" }, { env });
  assert.deepEqual([inside.enabled, inside.reason], [true, "percentage:1<20"]);
  const outside = evaluate(config, "new-checkout", { userId: "user-1", country: "US" }, { env });
  assert.deepEqual([outside.enabled, outside.reason], [false, "no-match"]);
  const rules = config.flags.get("new-checkout")?.rules ?? [];
  assert.equal(rules[0].type, "allowlist");
  assert.deepEqual(rules[rules.length - 1], { type: "percentage", percent: 20 });
});

test("the other storefront flags are unchanged", () => {
  const config = loadConfig(STOREFRONT);
  assert.equal(evaluate(config, "search-v2", { userId: "alice", country: "FR" }, { env }).reason, "percentage:6<10");
  assert.equal(evaluate(config, "search-v2", { userId: "user-1", country: "FR" }, { env }).enabled, false);
  assert.equal(evaluate(config, "gift-cards", { country: "FR" }, { env }).reason, "disabled");
  assert.equal(evaluate(config, "dark-mode", {}, { env }).reason, "everyone");
});
