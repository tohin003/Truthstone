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

test("loadConfig rejects a flag defined twice in the file, naming the flag", () => {
  // JSON.parse silently keeps the last of two equal keys: that is how the second "new-checkout"
  // block in storefront.json replaced the first one in October. See the README, Config.
  assert.throws(
    () => loadConfig(fixture("duplicate-flag.json")),
    (error: unknown) => error instanceof ConfigError && /duplicate-flag\.json: flag "new-checkout" is defined twice/.test(error.message),
  );
});
