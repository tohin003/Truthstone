// The schema's key grammar: lower-case words of letters and digits joined by single dots or hyphens.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const one = (key: string) => parseConfig({ flags: { [key]: { enabled: true } } });

test("a slash is not allowed in a flag key, and the error names the flag", () => {
  for (const key of ["checkout/one-page", "search/typo-tolerance", "a/b"]) {
    assert.throws(
      () => one(key),
      (error: unknown) => error instanceof ConfigError && error.message.includes(`flag ${JSON.stringify(key)}`),
      key,
    );
  }
});

test("keys that break the documented grammar in other ways are refused too", () => {
  for (const key of ["New-Checkout", "new_checkout", "new--checkout", "-new", "new.", "checkout/", "/checkout", "new checkout", ""]) {
    assert.throws(() => one(key), ConfigError, JSON.stringify(key));
  }
});

test("dotted and hyphenated keys are accepted", () => {
  for (const key of ["new-checkout", "search.v2", "a1.b2-c3", "x"]) {
    assert.deepEqual([...one(key).flags.keys()], [key]);
  }
});

test("the shipped example configs still load and evaluate", () => {
  const storefront = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));
  assert.equal(evaluate(storefront, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  const mobile = loadConfig(fileURLToPath(new URL("../flags/mobile.json", import.meta.url)));
  assert.equal(evaluate(mobile, "one-tap-reorder", { plan: "plus" }, { env: {} }).reason, "plan:hit");
});
