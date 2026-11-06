// evaluateAll: every flag of a config, decided exactly as evaluate() decides it, as { enabled, reason }.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as flagkit from "../src/index.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate, evaluateAll } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 10 }] },
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "country", values: ["DE", "AT"] },
      ],
    },
    "gift-cards": { enabled: false, rules: [{ type: "country", values: ["DE"] }] },
    "dark-mode": { enabled: true },
  },
});
const KEYS = ["search-v2", "new-checkout", "gift-cards", "dark-mode"];

test("every flag, in config order, as { enabled, reason }", () => {
  const all = evaluateAll(config, { userId: "alice", country: "AT" }, { env: {} });
  assert.deepEqual(Object.keys(all), KEYS);
  assert.deepEqual(all, {
    "search-v2": { enabled: true, reason: "percentage:6<10" },
    "new-checkout": { enabled: true, reason: "country:hit" },
    "gift-cards": { enabled: false, reason: "disabled" },
    "dark-mode": { enabled: true, reason: "everyone" },
  });
});

test("each state is what evaluate() says, without the trace", () => {
  for (const context of [{}, { userId: "qa-anna" }, { userId: "user-1", country: "FR" }, { userId: "user-3", plan: "plus" }]) {
    const all = evaluateAll(config, context, { env: {} });
    for (const key of KEYS) {
      const one = evaluate(config, key, context, { env: {} });
      assert.deepEqual(all[key], { enabled: one.enabled, reason: one.reason }, `${key} ${JSON.stringify(context)}`);
    }
  }
});

test("env overrides apply, from options.env", () => {
  const all = evaluateAll(config, { userId: "qa-anna" }, { env: { FLAGKIT_GIFT_CARDS: "on", FLAGKIT_NEW_CHECKOUT: "off" } });
  assert.deepEqual(all["gift-cards"], { enabled: true, reason: "override:on" });
  assert.deepEqual(all["new-checkout"], { enabled: false, reason: "override:off" });
  assert.deepEqual(all["dark-mode"], { enabled: true, reason: "everyone" });
});

test("without options the overrides come from process.env, and the context defaults to {}", () => {
  process.env.FLAGKIT_DARK_MODE = "off";
  try {
    const all = evaluateAll(config);
    assert.deepEqual(all["dark-mode"], { enabled: false, reason: "override:off" });
    assert.deepEqual(all["search-v2"], { enabled: false, reason: "no-match" });
  } finally {
    delete process.env.FLAGKIT_DARK_MODE;
  }
});

test("a config without flags gives an empty object", () => {
  assert.deepEqual(evaluateAll(parseConfig({ flags: {} }), {}, { env: {} }), {});
});

test("evaluateAll is part of the public API and the README", () => {
  assert.equal(typeof (flagkit as Record<string, unknown>).evaluateAll, "function");
  const all = (flagkit as unknown as { evaluateAll: typeof evaluateAll }).evaluateAll(config, {}, { env: {} });
  assert.deepEqual(all["dark-mode"], { enabled: true, reason: "everyone" });
  assert.match(readFileSync(new URL("../README.md", import.meta.url), "utf8"), /evaluateAll/);
});

test("evaluate itself is unchanged", () => {
  assert.deepEqual(evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} }).trace.length, 1);
  assert.equal(evaluate(config, "nope", {}, { env: {} }).reason, "unknown-flag");
});
