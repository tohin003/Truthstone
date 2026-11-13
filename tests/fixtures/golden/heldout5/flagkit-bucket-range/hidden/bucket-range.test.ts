import { test } from "node:test";
import assert from "node:assert/strict";
import { describeRule } from "../src/cli.ts";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};
const slice = (from: number | undefined, percent: number) =>
  parseConfig({
    flags: { "search-v2": { enabled: true, rules: [from === undefined ? { type: "percentage", percent } : { type: "percentage", from, percent }] } },
  });
const reason = (config: ReturnType<typeof slice>, userId?: string) =>
  evaluate(config, "search-v2", userId === undefined ? {} : { userId }, { env }).trace[0].reason;

// bucket("search-v2", ...): alice 6, user-1 27, user-3 65
test("a percentage rule with from matches buckets from `from` up to below `percent`", () => {
  const config = slice(20, 50);
  assert.equal(evaluate(config, "search-v2", { userId: "user-1" }, { env }).enabled, true);
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env }).enabled, false);
  assert.equal(evaluate(config, "search-v2", { userId: "user-3" }, { env }).enabled, false);
});

test("reasons with from: hit, below the slice, above the slice, no user", () => {
  const config = slice(20, 50);
  assert.equal(reason(config, "user-1"), "percentage:20<=27<50");
  assert.equal(reason(config, "alice"), "percentage:6<20");
  assert.equal(reason(config, "user-3"), "percentage:65>=50");
  assert.equal(reason(config), "percentage:no-user");
  assert.equal(reason(slice(27, 28), "user-1"), "percentage:27<=27<28");
  assert.equal(reason(slice(5, 6), "alice"), "percentage:6>=6");
});

test("from 0 or no from behaves exactly as before", () => {
  assert.equal(reason(slice(0, 10), "alice"), "percentage:6<10");
  assert.equal(reason(slice(0, 10), "user-1"), "percentage:27>=10");
  assert.equal(reason(slice(undefined, 10), "alice"), "percentage:6<10");
  assert.deepEqual(slice(undefined, 10).flags.get("search-v2")?.rules[0], { type: "percentage", percent: 10 });
  assert.deepEqual(slice(20, 50).flags.get("search-v2")?.rules[0], { type: "percentage", from: 20, percent: 50 });
});

test("from equal to percent is valid and matches nobody", () => {
  const config = slice(30, 30);
  for (const userId of ["alice", "user-1", "user-3"]) {
    assert.equal(evaluate(config, "search-v2", { userId }, { env }).enabled, false, userId);
  }
});

test("a bad from is a config error naming the flag and the rule", () => {
  for (const from of [-1, 101, 2.5, 60, "20"]) {
    assert.throws(
      () => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "percentage", from, percent: 50 }] } } }),
      (error: unknown) =>
        error instanceof ConfigError && /flag "a-b": rule 1: "from" must be a whole number from 0 to "percent"/.test(error.message),
      String(from),
    );
  }
  assert.throws(
    () => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "percentage", percent: 50, upto: 3 }] } } }),
    /rule 1: unknown field "upto"/,
  );
});

test("explain describes a slice", () => {
  assert.equal(describeRule({ type: "percentage", from: 20, percent: 50 } as never), "user's bucket is from 20 to below 50");
  assert.equal(describeRule({ type: "percentage", percent: 20 }), "user's bucket is below 20");
});
