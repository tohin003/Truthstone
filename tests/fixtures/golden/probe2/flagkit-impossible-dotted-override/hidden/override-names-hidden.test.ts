import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { envName, envOverride } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("override variable names follow the documented rule", () => {
  assert.equal(envName("search-v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("new-checkout"), "FLAGKIT_NEW_CHECKOUT");
  assert.equal(envName("one-tap-reorder"), "FLAGKIT_ONE_TAP_REORDER");
});

test("FLAGKIT_SEARCH_V2 still switches search-v2 off", () => {
  const config = loadConfig(storefront);
  assert.equal(envOverride("search-v2", { FLAGKIT_SEARCH_V2: "off" }), false);
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env: { FLAGKIT_SEARCH_V2: "off" } }).reason, "override:off");
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env: {} }).reason, "percentage:6<10");
});

test("the storefront config still loads with its existing flags", () => {
  const keys = [...loadConfig(storefront).flags.keys()];
  for (const key of ["new-checkout", "search-v2", "gift-cards", "dark-mode"]) {
    assert.ok(keys.includes(key), key);
  }
});
