import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";

function problems(run: () => unknown): string[] {
  try {
    run();
  } catch (error) {
    assert.ok(error instanceof ConfigError, String(error));
    const list = (error as ConfigError & { problems: unknown }).problems;
    assert.ok(Array.isArray(list), "ConfigError has a problems array");
    assert.equal(error.message, (list as string[]).join("\n"));
    return list as string[];
  }
  assert.fail("expected a ConfigError");
}

test("every flag's problems, in config order, valid flags skipped", () => {
  const input = {
    flags: {
      "search.v3": { enabled: true, rules: { type: "plan" } },
      "dark-mode": { enabled: true },
      "Promo_Bar": { enabled: "true", colour: "red", owner: "web", description: ["x"] },
      "gift-cards": {
        enabled: false,
        rules: [
          { type: "country", values: ["DE"] },
          { type: "allowlist", values: [] },
          { type: "percentage", percent: -1, salt: "x" },
          { type: 7 },
        ],
      },
    },
  };
  assert.deepEqual(problems(() => parseConfig(input)), [
    'flag "search.v3": "rules" must be an array',
    'flag "Promo_Bar": flag keys are lower-case letters and digits, separated by single dots or hyphens',
    'flag "Promo_Bar": unknown field "colour"',
    'flag "Promo_Bar": unknown field "owner"',
    'flag "Promo_Bar": "enabled" must be true or false',
    'flag "Promo_Bar": "description" must be a string',
    'flag "gift-cards": rule 2: "values" must be a non-empty list of user ids',
    'flag "gift-cards": rule 3: unknown field "salt"',
    'flag "gift-cards": rule 4: unknown rule type 7',
  ]);
});

test("top-level problems, then flags", () => {
  assert.deepEqual(problems(() => parseConfig(["flags"])), ["a config must be a JSON object"]);
  assert.deepEqual(problems(() => parseConfig({ version: 2, flags: [] })), [
    'unknown top-level key "version"',
    '"flags" must be an object of flag definitions',
  ]);
  assert.deepEqual(problems(() => parseConfig({ flags: { "a-b": "on", "c-d": { enabled: true, rules: [{ type: "weekday" }] } } })), [
    'flag "a-b": must be an object',
    'flag "c-d": rule 1: unknown rule type "weekday"',
  ]);
});

test("one problem reads exactly as before", () => {
  assert.deepEqual(problems(() => parseConfig({ flags: { "a-b": {} } })), ['flag "a-b": "enabled" must be true or false']);
  assert.throws(() => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "plan", values: ["x"], negate: true }] } } }), {
    message: 'flag "a-b": rule 1: unknown field "negate"',
  });
});

test("loadConfig puts the file name in front of every problem", () => {
  const dir = mkdtempSync(join(tmpdir(), "fk-problems-"));
  const path = join(dir, "flags.json");
  writeFileSync(path, JSON.stringify({ flagz: {}, flags: { "a-b": { enabled: 1 }, "c-d": { enabled: true } } }));
  assert.deepEqual(problems(() => loadConfig(path)), [
    `${path}: unknown top-level key "flagz"`,
    `${path}: flag "a-b": "enabled" must be true or false`,
  ]);
  writeFileSync(path, "{ not json");
  assert.match(problems(() => loadConfig(path))[0], /flags\.json is not valid JSON/);
});

test("valid configs still parse", () => {
  const config = parseConfig({
    flags: {
      "new-checkout": { enabled: true, description: "x", rules: [{ type: "allowlist", values: ["qa-anna"] }, { type: "percentage", percent: 20 }] },
      "dark-mode": { enabled: false },
    },
  });
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "dark-mode"]);
  assert.deepEqual(config.flags.get("dark-mode"), { key: "dark-mode", enabled: false, description: "", rules: [] });
  assert.deepEqual(config.flags.get("new-checkout")?.rules[1], { type: "percentage", percent: 20 });
});
