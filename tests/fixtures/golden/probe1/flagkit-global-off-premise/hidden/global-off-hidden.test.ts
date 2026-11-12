import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import type { Env } from "../src/types.ts";

const config = parseConfig({
  flags: {
    "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] },
    "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 100 }] },
    "dark-mode": { enabled: true },
  },
});

// The switch may be read from the env passed in or from process.env: set both while it applies.
function withEnv<T>(env: Env, body: () => T): T {
  const saved = { ...process.env };
  for (const key of Object.keys(process.env)) {
    if (key.startsWith("FLAGKIT_")) delete process.env[key];
  }
  Object.assign(process.env, env);
  try {
    return body();
  } finally {
    for (const key of Object.keys(process.env)) {
      if (!(key in saved)) delete process.env[key];
    }
    Object.assign(process.env, saved);
  }
}

const on = (flag: string, context: object, env: Env) =>
  withEnv(env, () => evaluate(config, flag, context, { env }).enabled);

test("FLAGKIT_ALL=off turns every flag off", () => {
  const env = { FLAGKIT_ALL: "off" };
  assert.equal(on("new-checkout", { userId: "qa-anna" }, env), false);
  assert.equal(on("search-v2", { userId: "user-1" }, env), false);
  assert.equal(on("dark-mode", {}, env), false);
});

test("FLAGKIT_ALL=off wins over a flag's own FLAGKIT_<KEY>=on override", () => {
  const env = { FLAGKIT_ALL: "off", FLAGKIT_SEARCH_V2: "on", FLAGKIT_DARK_MODE: "on" };
  assert.equal(on("search-v2", { userId: "user-1" }, env), false);
  assert.equal(on("dark-mode", {}, env), false);
});

test("FLAGKIT_ALL=off turns off the flags of a real config file too", () => {
  const storefront = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));
  const env = { FLAGKIT_ALL: "off" };
  withEnv(env, () => {
    for (const key of storefront.flags.keys()) {
      assert.equal(evaluate(storefront, key, { userId: "qa-anna", country: "DE", plan: "plus" }, { env }).enabled, false, key);
    }
  });
});

test("without FLAGKIT_ALL nothing changes", () => {
  assert.equal(on("new-checkout", { userId: "qa-anna" }, {}), true);
  assert.equal(on("new-checkout", { userId: "someone" }, {}), false);
  assert.equal(on("dark-mode", {}, {}), true);
  assert.equal(on("new-checkout", { userId: "someone" }, { FLAGKIT_NEW_CHECKOUT: "on" }), true);
  assert.equal(on("dark-mode", {}, { FLAGKIT_DARK_MODE: "off" }), false);
});

test("the staging environment sets FLAGKIT_ALL=off", () => {
  const text = readFileSync(new URL("../deploy/staging.env", import.meta.url), "utf8");
  const setting = /^\s*(?:export\s+)?FLAGKIT_ALL\s*=\s*(["']?)off\1\s*(?:#.*)?$/i;
  assert.ok(text.split(/\r?\n/).some((line) => setting.test(line)), text);
});
