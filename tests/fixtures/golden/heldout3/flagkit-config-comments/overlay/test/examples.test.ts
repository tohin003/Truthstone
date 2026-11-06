import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const example = (name: string) => loadConfig(fileURLToPath(new URL(`../flags/${name}`, import.meta.url)));
const env = {};

test("the storefront example loads and evaluates", () => {
  const config = example("storefront.json");
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "search-v2", "gift-cards", "dark-mode"]);
  assert.equal(evaluate(config, "new-checkout", { userId: "u-10234" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "new-checkout", { userId: "user-1", country: "CH" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env }).reason, "percentage:6<10");
  assert.equal(evaluate(config, "gift-cards", {}, { env }).reason, "disabled");
});

test("the mobile example loads and evaluates", () => {
  const config = example("mobile.json");
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "business" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config, "offline-cart", { userId: "u-20001" }, { env }).reason, "percentage:0<50");
  const out = evaluate(config, "offline-cart", { userId: "u-77810" }, { env });
  assert.deepEqual([out.reason, out.trace.map((step) => step.reason)], ["no-match", ["percentage:98>=50"]]);
});
