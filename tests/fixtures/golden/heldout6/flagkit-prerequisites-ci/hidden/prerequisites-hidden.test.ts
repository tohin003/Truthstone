import { test } from "node:test";
import assert from "node:assert/strict";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "wallet-v2": { enabled: true, requires: "payments.core", rules: [{ type: "allowlist", values: ["u-1"] }] },
    "payments.core": { enabled: true, rules: [{ type: "plan", values: ["business"] }] },
    "wallet-tips": { enabled: false, requires: "payments.core" },
    "wallet-badge": { enabled: true, requires: "wallet-v2" },
  },
});
const env = {};

test("an off prerequisite turns the flag off with its key as the reason", () => {
  assert.deepEqual(evaluate(config, "wallet-v2", { userId: "u-1", plan: "free" }, { env }), {
    flag: "wallet-v2",
    enabled: false,
    reason: "prerequisite:payments.core",
    trace: [],
  });
  assert.equal(evaluate(config, "wallet-v2", { userId: "u-1", plan: "business" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "wallet-v2", { userId: "u-2", plan: "business" }, { env }).reason, "no-match");
});

test("the enabled switch and the flag's own override come before the prerequisite", () => {
  assert.equal(evaluate(config, "wallet-tips", { plan: "free" }, { env }).reason, "disabled");
  assert.equal(evaluate(config, "wallet-v2", { plan: "free" }, { env: { FLAGKIT_WALLET_V2: "on" } }).reason, "override:on");
  assert.equal(
    evaluate(config, "wallet-v2", { userId: "u-1", plan: "business" }, { env: { FLAGKIT_PAYMENTS_CORE: "off" } }).reason,
    "prerequisite:payments.core",
  );
});

test("chains are followed to the end", () => {
  assert.equal(evaluate(config, "wallet-badge", { userId: "u-1", plan: "free" }, { env }).reason, "prerequisite:wallet-v2");
  assert.equal(evaluate(config, "wallet-badge", { userId: "u-1", plan: "business" }, { env }).reason, "everyone");
});

test("flags without prerequisites parse and evaluate as before", () => {
  const plain = parseConfig({ flags: { "dark-mode": { enabled: false } } });
  assert.deepEqual(plain.flags.get("dark-mode"), { key: "dark-mode", enabled: false, description: "", rules: [] });
});

test("unknown prerequisites and cycles are config errors", () => {
  assert.throws(
    () => parseConfig({ flags: { "x-y": { enabled: true, requires: "missing-flag" } } }),
    (error: unknown) => error instanceof ConfigError && /flag "x-y": requires unknown flag "missing-flag"/.test(error.message),
  );
  assert.throws(
    () => parseConfig({ flags: { first: { enabled: true, requires: "second" }, second: { enabled: true, requires: "first" } } }),
    (error: unknown) => error instanceof ConfigError && /flag "first": prerequisite cycle first -> second -> first/.test(error.message),
  );
  assert.throws(
    () =>
      parseConfig({
        flags: {
          lead: { enabled: true, requires: "p" },
          q: { enabled: true, requires: "r" },
          p: { enabled: true, requires: "q" },
          r: { enabled: true, requires: "p" },
        },
      }),
    /flag "q": prerequisite cycle q -> r -> p -> q/,
  );
});
