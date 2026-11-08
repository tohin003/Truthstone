import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

function problems(run: () => unknown): string[] {
  try {
    run();
  } catch (error) {
    assert.ok(error instanceof ConfigError, String(error));
    const list = (error as ConfigError & { problems: string[] }).problems;
    assert.ok(Array.isArray(list), "ConfigError has a problems array");
    assert.equal(error.message, list.join("\n"));
    return list;
  }
  assert.fail("expected a ConfigError");
}

test("every problem in a config is reported, in config order", () => {
  const input = {
    flags: {
      "a-b": { enabled: "yes", rules: [{ type: "weekday" }, { type: "country", values: ["de"] }] },
      "ok-flag": { enabled: true },
      "Bad Key": { enabled: true, owner: "me" },
      "c-d": { enabled: true, description: 7, rules: [{ type: "percentage", percent: 101 }, { type: "plan", values: ["plus"] }] },
    },
  };
  assert.deepEqual(problems(() => parseConfig(input)), [
    'flag "a-b": "enabled" must be true or false',
    'flag "a-b": rule 1: unknown rule type "weekday"',
    'flag "a-b": rule 2: "values" must be a non-empty list of two-letter upper-case country codes',
    'flag "Bad Key": flag keys are lower-case letters and digits, separated by single dots or hyphens',
    'flag "Bad Key": unknown field "owner"',
    'flag "c-d": "description" must be a string',
    'flag "c-d": rule 1: "percent" must be a whole number from 0 to 100',
  ]);
});

test("top-level problems come first", () => {
  assert.deepEqual(problems(() => parseConfig({ flagz: {}, flags: { "x-y": { enabled: 1 } }, extra: true })), [
    'unknown top-level key "flagz"',
    'unknown top-level key "extra"',
    'flag "x-y": "enabled" must be true or false',
  ]);
  assert.deepEqual(problems(() => parseConfig({ flagz: {} })), [
    'unknown top-level key "flagz"',
    '"flags" must be an object of flag definitions',
  ]);
});

test("a flag that is not an object reports only that; a rule reports its first problem only", () => {
  assert.deepEqual(problems(() => parseConfig({ flags: { "a-b": [], "c-d": { enabled: true, rules: [{ type: "plan", values: [], negate: true }] } } })), [
    'flag "a-b": must be an object',
    'flag "c-d": rule 1: unknown field "negate"',
  ]);
});

test("a config with one problem reads as before", () => {
  assert.deepEqual(problems(() => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "weekday" }] } } })), [
    'flag "a-b": rule 1: unknown rule type "weekday"',
  ]);
});

test("loadConfig names the file in front of every problem", () => {
  const path = fixture("two-problems.json");
  assert.deepEqual(problems(() => loadConfig(path)), [
    `${path}: flag "beta-banner": rule 1: unknown rule type "weekday"`,
    `${path}: flag "promo-bar": unknown field "colour"`,
    `${path}: flag "promo-bar": "enabled" must be true or false`,
  ]);
});
