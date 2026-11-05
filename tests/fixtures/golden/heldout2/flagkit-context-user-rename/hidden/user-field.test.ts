import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { evaluate, loadConfig, MATCHERS } from "../src/index.ts";
import { runSmoke } from "../src/smoke.ts";

const path = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));
const storefront = path("../flags/storefront.json");
const env = {};

test("rules read the context's user", () => {
  const config = loadConfig(storefront);
  assert.equal(evaluate(config, "new-checkout", { user: "qa-anna" } as never, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "search-v2", { user: "alice" } as never, { env }).reason, "percentage:6<10");
  const flag = { key: "x", enabled: true, description: "", rules: [] };
  assert.equal(MATCHERS.allowlist({ type: "allowlist", values: ["u-1"] }, { user: "u-1" } as never, flag).matched, true);
});

test("userId is not read anymore", () => {
  const config = loadConfig(storefront);
  const result = evaluate(config, "search-v2", { userId: "alice" } as never, { env });
  assert.equal(result.reason, "no-match");
  assert.equal(result.trace[0].reason, "percentage:no-user");
});

test("the CLI's --user reaches the rules", () => {
  const result = spawnSync(process.execPath, [path("../src/cli.ts"), "eval", storefront, "new-checkout", "--user", "qa-anna"], { encoding: "utf8", env: { PATH: process.env.PATH ?? "" } });
  assert.equal(result.stdout.trim(), "on (allowlist:hit)");
});

test("the QA smoke file still passes", () => {
  const result = runSmoke(storefront, path("../qa/storefront-smoke.jsonl"));
  assert.deepEqual(result.failures, []);
  assert.equal(result.passed, 10);
  const config = loadConfig(storefront);
  assert.equal(evaluate(config, "new-checkout", { user: "user-1" } as never, { env }).trace[2].reason, "percentage:63>=20");
});
