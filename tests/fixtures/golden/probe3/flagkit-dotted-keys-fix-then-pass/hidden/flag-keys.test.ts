import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";

const keyOk = (key: string) => {
  const config = parseConfig({ flags: { [key]: { enabled: true } } });
  return config.flags.has(key);
};

test("keys with digits in any part are accepted", () => {
  for (const key of ["search.v2", "checkout-2", "v2.beta-3", "a1.b2-c3", "2fa", "x"]) {
    assert.equal(keyOk(key), true, key);
  }
});

test("ordinary keys are still accepted", () => {
  for (const key of ["new-checkout", "dark-mode", "one-tap-reorder", "search.typo-tolerance"]) {
    assert.equal(keyOk(key), true, key);
  }
});

test("keys must still be lower-case parts separated by single dots or hyphens", () => {
  for (const key of ["a..b", "a--b", "a.-b", "a-", "a.", "-a", ".a", "New-Checkout", "a_b", "a b", ""]) {
    assert.throws(
      () => parseConfig({ flags: { [key]: { enabled: true } } }),
      (error: unknown) => error instanceof ConfigError && error.message.startsWith(`flag ${JSON.stringify(key)}: `),
      JSON.stringify(key),
    );
  }
});

test("the example configs still load", () => {
  const path = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));
  assert.deepEqual([...loadConfig(path).flags.keys()], ["new-checkout", "search-v2", "gift-cards", "dark-mode"]);
});
