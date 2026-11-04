import { test } from "node:test";
import assert from "node:assert/strict";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};
type Ctx = Parameters<typeof evaluate>[2];
const ctx = (appVersion?: string, extra: Record<string, string> = {}) => ({ ...extra, appVersion }) as Ctx;

function configWith(range: unknown, more: object[] = []) {
  return parseConfig({ flags: { "new-player": { enabled: true, rules: [{ type: "version", range }, ...more] } } });
}

function decide(range: string, appVersion?: string) {
  return evaluate(configWith(range), "new-player", ctx(appVersion), { env });
}

test("a version rule matches app versions inside the range", () => {
  assert.equal(decide(">=2.3.0 <3.0.0", "2.3.0").reason, "version:hit");
  assert.equal(decide(">=2.3.0 <3.0.0", "2.9.9").enabled, true);
  assert.equal(decide("=2.3.1", "2.3.1").reason, "version:hit");
  assert.equal(decide(">1.0.0", "1.0.1").enabled, true);
  assert.equal(decide("<=4.0.0 >=4.0.0", "4.0.0").enabled, true);
});

test("versions outside the range miss", () => {
  for (const [range, version] of [
    [">=2.3.0 <3.0.0", "2.2.9"],
    [">=2.3.0 <3.0.0", "3.0.0"],
    ["=2.3.1", "2.3.0"],
    [">1.0.0", "1.0.0"],
    ["<1.0.0", "1.0.0"],
  ]) {
    const result = decide(range, version);
    assert.equal(result.enabled, false, `${version} in ${range}`);
    assert.deepEqual(result.trace.map((step) => step.reason), ["version:miss"]);
  }
});

test("versions compare numerically, not as text", () => {
  assert.equal(decide(">=2.9.0", "2.10.0").enabled, true);
  assert.equal(decide("<3.0.0", "10.0.0").enabled, false);
  assert.equal(decide(">=1.2.10", "1.2.9").enabled, false);
  assert.equal(decide(">=1.2.10 <1.3.0", "1.2.11").enabled, true);
});

test("a context without a well-formed appVersion does not match", () => {
  for (const version of [undefined, "2.3", "v2.3.0", "2.3.0-beta.1", "2.3.0.1", ""]) {
    assert.equal(decide(">=1.0.0", version).enabled, false, String(version));
  }
});

test("version rules combine with the other rules", () => {
  const config = configWith(">=3.0.0", [{ type: "country", values: ["DE"] }]);
  assert.equal(evaluate(config, "new-player", ctx("2.0.0", { country: "DE" }), { env }).reason, "country:hit");
  assert.equal(evaluate(config, "new-player", ctx("3.1.4", { country: "FR" }), { env }).reason, "version:hit");
});

const invalid: Array<[string, unknown]> = [
  ["a caret range", "^2.3.0"],
  ["a tilde range", "~2.3.0"],
  ["a bare version", "2.3.0"],
  ["a version without a patch", ">=2.3"],
  ["an x-range", ">=2.x.0"],
  ["a pre-release tag", ">=2.3.0-beta.1"],
  ["an or", ">=2.3.0 || <1.0.0"],
  ["a space after the operator", ">= 2.3.0"],
  ["an empty range", ""],
  ["a number", 2],
  ["no range at all", undefined],
];

for (const [name, range] of invalid) {
  test(`a range with ${name} is a config error naming the flag`, () => {
    assert.throws(
      () => configWith(range),
      (error: unknown) => error instanceof ConfigError && error.message.includes("new-player"),
    );
  });
}
