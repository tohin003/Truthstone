import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

// Checks on the configs we ship in flags/: they read the real files and pin real decisions, so
// they run on CI (CI=1 npm test), not in the quick local run. See README "Development".
const skip = process.env.CI ? false : "shipped-config checks run on CI only (CI=1 npm test)";
const dir = fileURLToPath(new URL("../flags/", import.meta.url));
const env = {};

test("every shipped config loads", { skip }, () => {
  for (const name of readdirSync(dir).filter((file) => file.endsWith(".json"))) {
    loadConfig(dir + name);
  }
});

test("storefront: DACH users get the new checkout by country", { skip }, () => {
  const config = loadConfig(dir + "storefront.json");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "CH" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "gift-cards", { country: "DE" }, { env }).reason, "disabled");
});

test("mobile: express pickup is on for users in Germany and Austria", { skip }, () => {
  const config = loadConfig(dir + "mobile.json");
  for (const country of ["DE", "AT", "de"]) {
    const result = evaluate(config, "express-pickup", { userId: "u-30017", country }, { env });
    assert.equal(result.enabled, true, country);
    assert.equal(result.reason, "country:hit", country);
  }
  assert.equal(evaluate(config, "express-pickup", { userId: "u-30017", country: "FR" }, { env }).enabled, false);
});
