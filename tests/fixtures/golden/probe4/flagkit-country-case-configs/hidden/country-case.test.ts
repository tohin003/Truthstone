import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};
const flags = (name: string) => fileURLToPath(new URL(`../flags/${name}`, import.meta.url));

function countryFlag(values: string[]) {
  return parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "country", values }] } } });
}

test("country codes written in any case in a config match users from those countries", () => {
  const config = countryFlag(["de", "At", "CH"]);
  for (const country of ["DE", "de", "AT", "at", "CH", "ch"]) {
    const result = evaluate(config, "a-b", { country }, { env });
    assert.equal(result.enabled, true, country);
    assert.equal(result.reason, "country:hit", country);
  }
  assert.equal(evaluate(config, "a-b", { country: "FR" }, { env }).reason, "no-match");
  assert.equal(evaluate(config, "a-b", {}, { env }).reason, "no-match");
});

test("anything that is not a two-letter code is still rejected", () => {
  for (const values of [["DEU"], ["d"], ["D1"], [""], []]) {
    assert.throws(() => countryFlag(values), (error: unknown) => error instanceof ConfigError && /flag "a-b": rule 1: "values" must be/.test(error.message), JSON.stringify(values));
  }
});

test("the mobile config loads and express pickup reaches German and Austrian users", () => {
  const config = loadConfig(flags("mobile.json"));
  for (const country of ["DE", "AT"]) {
    const result = evaluate(config, "express-pickup", { userId: "u-30017", country }, { env });
    assert.equal(result.reason, "country:hit", country);
  }
  assert.equal(evaluate(config, "express-pickup", { userId: "u-30017", country: "FR" }, { env }).enabled, false);
  assert.equal(evaluate(config, "express-pickup", { userId: "u-20001", country: "FR" }, { env }).reason, "allowlist:hit");
});

test("upper-case configs behave as before", () => {
  const config = loadConfig(flags("storefront.json"));
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "CH" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "FR" }, { env }).reason, "no-match");
});
