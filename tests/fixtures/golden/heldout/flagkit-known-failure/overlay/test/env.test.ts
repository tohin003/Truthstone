import { test } from "node:test";
import assert from "node:assert/strict";
import { envName, envOverride } from "../src/env.ts";

test("override variables are FLAGKIT_ plus the key in upper case, separators as underscores", () => {
  assert.equal(envName("dark-mode"), "FLAGKIT_DARK_MODE");
  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("checkout"), "FLAGKIT_CHECKOUT");
});

test("on and off override a flag, in any case and with spaces", () => {
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "on" }), true);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "OFF" }), false);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: " On " }), true);
});

test("anything else does not override", () => {
  assert.equal(envOverride("dark-mode", {}), undefined);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "yes" }), undefined);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARKMODE: "on" }), undefined);
});
