import { test } from "node:test";
import assert from "node:assert/strict";
import { envName, envOverride } from "../src/index.ts";

test("override names follow the documented derivation, for every key", () => {
  assert.equal(envName("beta.banner"), "FLAGKIT_BETA_BANNER");
  assert.equal(envName("beta-banner"), "FLAGKIT_BETA_BANNER");
  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("new-checkout"), "FLAGKIT_NEW_CHECKOUT");
  assert.equal(envName("a.b-c"), "FLAGKIT_A_B_C");
});

test("the documented variable overrides each flag it names", () => {
  const env = { FLAGKIT_BETA_BANNER: "off" };
  assert.equal(envOverride("beta.banner", env), false);
  assert.equal(envOverride("beta-banner", env), false);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: " ON " }), true);
});
