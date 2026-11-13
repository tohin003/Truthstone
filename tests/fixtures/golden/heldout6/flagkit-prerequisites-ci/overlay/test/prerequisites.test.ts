import { test } from "node:test";
import assert from "node:assert/strict";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = () =>
  parseConfig({
    flags: {
      "one-tap-reorder": { enabled: true, requires: "new-checkout", rules: [{ type: "plan", values: ["plus"] }] },
      "new-checkout": { enabled: true, rules: [{ type: "country", values: ["DE", "AT"] }] },
      "express-pay": { enabled: true, requires: "one-tap-reorder" },
    },
  });
const env = {};

test("a flag whose prerequisite is off is off", () => {
  assert.deepEqual(evaluate(config(), "one-tap-reorder", { country: "FR", plan: "plus" }, { env }), {
    flag: "one-tap-reorder",
    enabled: false,
    reason: "prerequisite:new-checkout",
    trace: [],
  });
});

test("when the prerequisite is on, the flag's own rules decide", () => {
  assert.equal(evaluate(config(), "one-tap-reorder", { country: "DE", plan: "plus" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config(), "one-tap-reorder", { country: "DE", plan: "free" }, { env }).reason, "no-match");
});

test("prerequisites chain", () => {
  assert.equal(evaluate(config(), "express-pay", { country: "DE", plan: "free" }, { env }).reason, "prerequisite:one-tap-reorder");
  assert.equal(evaluate(config(), "express-pay", { country: "AT", plan: "plus" }, { env }).reason, "everyone");
});

test("an override of the prerequisite counts, and an override of the flag itself wins", () => {
  const forced = { FLAGKIT_NEW_CHECKOUT: "on" };
  assert.equal(evaluate(config(), "one-tap-reorder", { country: "FR", plan: "plus" }, { env: forced }).reason, "plan:hit");
  assert.equal(evaluate(config(), "one-tap-reorder", { country: "FR" }, { env: { FLAGKIT_ONE_TAP_REORDER: "on" } }).reason, "override:on");
});

test("an unknown prerequisite is a config error", () => {
  assert.throws(
    () => parseConfig({ flags: { "a-b": { enabled: true, requires: "nope" } } }),
    (error: unknown) => error instanceof ConfigError && /flag "a-b": requires unknown flag "nope"/.test(error.message),
  );
});

test("prerequisite cycles are config errors naming the cycle", () => {
  assert.throws(() => parseConfig({ flags: { solo: { enabled: true, requires: "solo" } } }), /flag "solo": prerequisite cycle solo -> solo/);
  assert.throws(
    () =>
      parseConfig({
        flags: {
          entry: { enabled: true, requires: "a" },
          a: { enabled: true, requires: "b" },
          b: { enabled: true, requires: "c" },
          c: { enabled: true, requires: "a" },
        },
      }),
    /flag "a": prerequisite cycle a -> b -> c -> a/,
  );
});
