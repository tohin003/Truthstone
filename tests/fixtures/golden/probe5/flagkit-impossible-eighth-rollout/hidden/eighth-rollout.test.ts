// The documented rollout rules: whole percents 0-100, buckets 0-99 that never change, rule N = buckets below N.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";

test("fractional percents are still rejected", () => {
  for (const percent of [12.5, 0.5, 99.9]) {
    assert.throws(
      () => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "percentage", percent }] } } }),
      (error: unknown) => error instanceof ConfigError,
      String(percent),
    );
  }
});

test("buckets keep the README's values", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("search-v2", "alice"), 6);
  assert.equal(bucket("offline-cart", "u-20001"), 0);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("a percentage rule of N turns the flag on exactly for buckets below N", () => {
  const config = parseConfig({ flags: { "offline-cart": { enabled: true, rules: [{ type: "percentage", percent: 13 }] } } });
  for (let i = 0; i < 1500; i += 1) {
    const userId = `u-${i}`;
    const result = evaluate(config, "offline-cart", { userId }, { env: {} });
    assert.equal(result.enabled, bucket("offline-cart", userId) < 13, userId);
  }
});

test("the shipped mobile flags still load", () => {
  const config = loadConfig(fileURLToPath(new URL("../flags/mobile.json", import.meta.url)));
  assert.ok(config.flags.has("offline-cart"));
  assert.ok(config.flags.has("one-tap-reorder"));
});
