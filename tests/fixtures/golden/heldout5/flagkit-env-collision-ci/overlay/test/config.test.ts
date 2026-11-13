import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig, RULE_TYPES } from "../src/config.ts";

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

test("a config with every rule type parses", () => {
  const config = parseConfig({
    flags: {
      "new-checkout": {
        enabled: true,
        description: "checkout",
        rules: [
          { type: "allowlist", values: ["qa-anna"] },
          { type: "country", values: ["DE"] },
          { type: "plan", values: ["plus"] },
          { type: "percentage", percent: 25 },
        ],
      },
      "dark-mode": { enabled: false },
    },
  });
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "dark-mode"]);
  const checkout = config.flags.get("new-checkout");
  assert.equal(checkout?.rules.length, 4);
  assert.deepEqual(checkout?.rules[3], { type: "percentage", percent: 25 });
  assert.deepEqual(config.flags.get("dark-mode"), { key: "dark-mode", enabled: false, description: "", rules: [] });
});

test("the built-in rule types are known to validation", () => {
  for (const type of ["country", "plan", "allowlist", "percentage"]) {
    assert.ok(RULE_TYPES.includes(type), type);
  }
});

const invalid: Array<[string, unknown, RegExp]> = [
  ["not an object", [], /must be a JSON object/],
  ["unknown top-level key", { flags: {}, flagz: {} }, /unknown top-level key "flagz"/],
  ["flags not an object", { flags: [] }, /"flags" must be an object/],
  ["bad flag key", { flags: { "New Checkout": { enabled: true } } }, /flag "New Checkout": flag keys are/],
  ["missing enabled", { flags: { "a-b": {} } }, /flag "a-b": "enabled" must be true or false/],
  ["unknown flag field", { flags: { "a-b": { enabled: true, owner: "me" } } }, /flag "a-b": unknown field "owner"/],
  ["unknown rule type", { flags: { "a-b": { enabled: true, rules: [{ type: "weekday" }] } } }, /flag "a-b": rule 1: unknown rule type "weekday"/],
  ["lower-case country", { flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["de"] }] } } }, /flag "a-b": rule 1: "values" must be/],
  ["empty allowlist", { flags: { "a-b": { enabled: true, rules: [{ type: "allowlist", values: [] }] } } }, /flag "a-b": rule 1: "values" must be/],
  ["percent too big", { flags: { "a-b": { enabled: true, rules: [{ type: "percentage", percent: 101 }] } } }, /flag "a-b": rule 1: "percent" must be/],
  ["fractional percent", { flags: { "a-b": { enabled: true, rules: [{ type: "percentage", percent: 12.5 }] } } }, /"percent" must be/],
  ["unknown rule field", { flags: { "a-b": { enabled: true, rules: [{ type: "plan", values: ["x"], negate: true }] } } }, /rule 1: unknown field "negate"/],
];

for (const [name, input, message] of invalid) {
  test(`invalid config is rejected, naming the problem: ${name}`, () => {
    assert.throws(() => parseConfig(input), (error: unknown) => error instanceof ConfigError && message.test(error.message));
  });
}

test("loadConfig reads and validates a file", () => {
  const config = loadConfig(fixture("flags.json"));
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "gift-cards", "dark-mode"]);
});

test("loadConfig names the file in its errors", () => {
  assert.throws(() => loadConfig(fixture("missing.json")), /cannot read .*missing\.json: ENOENT/);
  assert.throws(() => loadConfig(fixture("broken.json")), /broken\.json is not valid JSON/);
  assert.throws(() => loadConfig(fixture("bad-rule.json")), /bad-rule\.json: flag "beta-banner": rule 1: unknown rule type "weekday"/);
});

test("flags that share an override variable are rejected, naming both and the variable", () => {
  assert.throws(
    () => parseConfig({ flags: { "search.v2": { enabled: true }, "search-v2": { enabled: false } } }),
    (error: unknown) =>
      error instanceof ConfigError &&
      error.message === 'flags "search.v2" and "search-v2" share the override variable FLAGKIT_SEARCH_V2',
  );
});

test("a collision is found whatever separates the words", () => {
  assert.throws(
    () => parseConfig({ flags: { "one-tap.reorder": { enabled: true }, "dark-mode": { enabled: true }, "one.tap-reorder": { enabled: true } } }),
    /flags "one-tap\.reorder" and "one\.tap-reorder" share the override variable FLAGKIT_ONE_TAP_REORDER/,
  );
});

test("flags with different override variables load", () => {
  const config = parseConfig({ flags: { "search-v2": { enabled: true }, "search-v3": { enabled: true }, "searchv2": { enabled: true } } });
  assert.equal(config.flags.size, 3);
});

test("loadConfig names the file when override variables collide", () => {
  assert.throws(() => loadConfig(fixture("collision.json")), /collision\.json: flags "checkout\.v2" and "checkout-v2" share the override variable FLAGKIT_CHECKOUT_V2/);
});
