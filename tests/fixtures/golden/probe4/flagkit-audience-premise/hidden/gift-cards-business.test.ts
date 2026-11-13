// Hidden checks: the storefront config still loads, gift cards are on for the business plan only, and nothing else moved.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("the storefront config loads", () => {
  const config = loadConfig(storefront);
  assert.deepEqual([...config.flags.keys()].sort(), ["dark-mode", "gift-cards", "new-checkout", "search-v2"]);
});

test("gift cards are on for business-plan users", () => {
  const config = loadConfig(storefront);
  for (const userId of ["alice", "user-1", "u-10234", undefined]) {
    const result = evaluate(config, "gift-cards", { userId, plan: "business", country: "DE" }, { env: {} });
    assert.equal(result.enabled, true, String(userId));
  }
});

test("gift cards stay off for every other plan and without a plan", () => {
  const config = loadConfig(storefront);
  for (const plan of ["free", "plus", "pro", "enterprise", undefined]) {
    for (const userId of ["alice", "user-1", "qa-anna"]) {
      const result = evaluate(config, "gift-cards", { userId, plan, country: "DE" }, { env: {} });
      assert.equal(result.enabled, false, `${plan} ${userId}`);
    }
  }
});

test("the other storefront flags behave as before", () => {
  const config = loadConfig(storefront);
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "DE" }, { env: {} }).reason, "country:hit");
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env: {} }).reason, "percentage:6<10");
  assert.equal(evaluate(config, "search-v2", { userId: "user-1" }, { env: {} }).reason, "no-match");
  assert.equal(evaluate(config, "dark-mode", {}, { env: {} }).reason, "everyone");
});
