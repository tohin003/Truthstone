import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { bucket } from "../src/hash.ts";
import { main } from "../src/cli.ts";

const env = {};
const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("the example configs still load and evaluate as documented", () => {
  const config = loadConfig(storefront);
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env }).reason, "percentage:6<10");
  assert.equal(evaluate(config, "gift-cards", {}, { env }).reason, "disabled");
  assert.equal(evaluate(config, "dark-mode", {}, { env }).reason, "everyone");
});

test("validation errors and missing files are still reported", () => {
  assert.throws(() => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "weekday" }] } } }), ConfigError);
  assert.throws(() => loadConfig("no-such-config.json"), /cannot read no-such-config\.json: ENOENT/);
});

test("buckets are unchanged", () => {
  assert.equal(bucket("new-checkout", "user-1"), 63);
  assert.equal(bucket("offline-cart", "u-77810"), 98);
});

test("the CLI still evaluates a flag", () => {
  let out = "";
  const status = main(["eval", storefront, "dark-mode"], { stdout: { write: (text: string) => (out += text) }, stderr: { write: () => true }, env });
  assert.equal(status, 0);
  assert.equal(out, "on (everyone)\n");
});
