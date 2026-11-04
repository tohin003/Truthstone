import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { loadConfig } from "../src/config.ts";
import { envName, envOverride } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

const MOBILE = fileURLToPath(new URL("../flags/mobile.json", import.meta.url));

test("every hyphen and dot in a key becomes an underscore", () => {
  assert.equal(envName("one-tap-reorder"), "FLAGKIT_ONE_TAP_REORDER");
  assert.equal(envName("a-b-c-d"), "FLAGKIT_A_B_C_D");
  assert.equal(envName("search.v2.beta"), "FLAGKIT_SEARCH_V2_BETA");
  assert.equal(envName("checkout.express-pay"), "FLAGKIT_CHECKOUT_EXPRESS_PAY");
  assert.equal(envName("checkout.express-pay.v2"), "FLAGKIT_CHECKOUT_EXPRESS_PAY_V2");
});

test("simple keys map as before", () => {
  assert.equal(envName("new-checkout"), "FLAGKIT_NEW_CHECKOUT");
  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("checkout"), "FLAGKIT_CHECKOUT");
  assert.equal(envName("v2"), "FLAGKIT_V2");
});

test("overrides work for keys with several separators", () => {
  assert.equal(envOverride("one-tap-reorder", { FLAGKIT_ONE_TAP_REORDER: "off" }), false);
  assert.equal(envOverride("search.v2.beta", { FLAGKIT_SEARCH_V2_BETA: "ON" }), true);
  assert.equal(envOverride("one-tap-reorder", { "FLAGKIT_ONE_TAP-REORDER": "off" }), undefined);
});

test("override values are read as before", () => {
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: " On " }), true);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "yes" }), undefined);
  assert.equal(envOverride("dark-mode", {}), undefined);
});

test("an override turns off one-tap-reorder from the mobile config", () => {
  const config = loadConfig(MOBILE);
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "plus" }, { env: {} }).reason, "plan:hit");
  const result = evaluate(config, "one-tap-reorder", { plan: "plus" }, { env: { FLAGKIT_ONE_TAP_REORDER: "off" } });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "override:off");
});

test("the CLI honours the override", () => {
  let stdout = "";
  const status = main(["eval", MOBILE, "one-tap-reorder", "--plan", "plus"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: () => true },
    env: { FLAGKIT_ONE_TAP_REORDER: "off" },
  });
  assert.equal(status, 0);
  assert.equal(stdout, "off (override:off)\n");
});
