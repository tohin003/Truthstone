import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const fromRoot = (rel: string) => fileURLToPath(new URL(`../${rel}`, import.meta.url));
const env = {};

test("search-v2 is off for everyone in the storefront config", () => {
  const config = loadConfig(fromRoot("flags/storefront.json"));
  assert.ok(config.flags.has("search-v2"), "search-v2 is still defined");
  // bucket("search-v2", "alice") is 6, below the 10% rollout
  for (const userId of ["alice", "user-1", "user-3", "qa-anna", "u-10234"]) {
    const result = evaluate(config, "search-v2", { userId, country: "DE", plan: "plus" }, { env });
    assert.equal(result.enabled, false, userId);
    assert.notEqual(result.reason, "unknown-flag");
  }
  assert.equal(evaluate(config, "search-v2", {}, { env }).enabled, false);
});

test("the other storefront flags are unchanged", () => {
  const config = loadConfig(fromRoot("flags/storefront.json"));
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "CH" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "dark-mode", {}, { env }).reason, "everyone");
  assert.equal(evaluate(config, "gift-cards", {}, { env }).reason, "disabled");
});

test("the mobile config still loads", () => {
  assert.equal(loadConfig(fromRoot("flags/mobile.json")).flags.size, 2);
});
