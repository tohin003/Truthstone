import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";

const config = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));

// Users in wave 1 today (search-v2 buckets 0-9).
const WAVE_ONE = ["alice", "u-1033", "u-1036", "u-1052", "u-1071", "u-1100", "u-1125", "u-1142", "u-1166", "u-1010", "u-1044", "u-1087"];

test("nobody who has search-v2 today loses it", () => {
  for (const userId of WAVE_ONE) {
    assert.equal(evaluate(config, "search-v2", { userId }, { env: {} }).enabled, true, userId);
  }
});

test("buckets are unchanged (analytics joins on them)", () => {
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("search-v2", "user-1"), 27);
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
  assert.equal(bucket("search-v2", "u-1071"), 5);
});

test("the other storefront flags are untouched", () => {
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "gift-cards", {}, { env: {} }).reason, "disabled");
  assert.equal(evaluate(config, "dark-mode", {}, { env: {} }).reason, "everyone");
});
