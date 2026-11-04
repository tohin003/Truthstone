import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { ConfigError, loadConfig, parseConfig, RULE_TYPES } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { matcherFor } from "../src/matchers.ts";

const fromRoot = (rel: string) => fileURLToPath(new URL(`../${rel}`, import.meta.url));
const env = {};

function cli(argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: (text: string) => (stderr += text) },
    env: {},
  });
  return { status, stdout, stderr };
}

test("userIds rules match listed users, with userIds reasons", () => {
  const config = parseConfig({ flags: { beta: { enabled: true, rules: [{ type: "userIds", values: ["u-1", "u-2"] }] } } });
  const hit = evaluate(config, "beta", { userId: "u-2" }, { env });
  assert.equal(hit.enabled, true);
  assert.equal(hit.reason, "userIds:hit");
  const miss = evaluate(config, "beta", { userId: "u-3" }, { env });
  assert.equal(miss.enabled, false);
  assert.deepEqual(miss.trace.map((step) => step.reason), ["userIds:miss"]);
});

test("userIds rules are validated like the other list rules", () => {
  assert.throws(() => parseConfig({ flags: { beta: { enabled: true, rules: [{ type: "userIds", values: [] }] } } }), ConfigError);
  assert.throws(() => parseConfig({ flags: { beta: { enabled: true, rules: [{ type: "userIds", values: [42] }] } } }), ConfigError);
});

test("allowlist is gone: a config that still uses it fails validation", () => {
  assert.throws(
    () => parseConfig({ flags: { beta: { enabled: true, rules: [{ type: "allowlist", values: ["u-1"] }] } } }),
    (error: unknown) => error instanceof ConfigError && error.message.includes("beta"),
  );
});

test("userIds is a known rule type with a matcher, and allowlist is neither", () => {
  assert.ok(RULE_TYPES.includes("userIds"));
  assert.ok(!RULE_TYPES.includes("allowlist"));
  assert.doesNotThrow(() => matcherFor("userIds"));
  assert.throws(() => matcherFor("allowlist"));
});

test("the shipped example configs load", () => {
  for (const name of ["flags/storefront.json", "flags/mobile.json"]) {
    assert.doesNotThrow(() => loadConfig(fromRoot(name)), name);
  }
});

test("the example configs still target their users by id", () => {
  const storefront = loadConfig(fromRoot("flags/storefront.json"));
  assert.equal(evaluate(storefront, "new-checkout", { userId: "qa-anna", country: "FR" }, { env }).reason, "userIds:hit");
  const mobile = loadConfig(fromRoot("flags/mobile.json"));
  assert.equal(evaluate(mobile, "one-tap-reorder", { userId: "u-20001", plan: "free" }, { env }).reason, "userIds:hit");
});

test("the README's example config is valid", () => {
  const readme = readFileSync(fromRoot("README.md"), "utf8");
  const block = /```json\n([\s\S]*?)```/.exec(readme);
  assert.ok(block, "the README has a json example");
  assert.doesNotThrow(() => parseConfig(JSON.parse(block[1])));
});

test("the CLI help no longer mentions allowlist", () => {
  const { status, stdout } = cli(["--help"]);
  assert.equal(status, 0);
  assert.doesNotMatch(stdout, /allowlist/i);
});

test("explain shows a userIds rule deciding", () => {
  const { status, stdout } = cli(["explain", fromRoot("flags/storefront.json"), "new-checkout", "--user", "qa-ben"]);
  assert.equal(status, 0);
  assert.match(stdout, /^new-checkout: on \(userIds:hit\)$/m);
});

test("the other rule types are unchanged", () => {
  const config = parseConfig({
    flags: {
      x: {
        enabled: true,
        rules: [
          { type: "country", values: ["DE"] },
          { type: "plan", values: ["plus"] },
          { type: "percentage", percent: 100 },
        ],
      },
    },
  });
  assert.equal(evaluate(config, "x", { country: "DE" }, { env }).reason, "country:hit");
  assert.equal(evaluate(config, "x", { plan: "plus" }, { env }).reason, "plan:hit");
  assert.match(evaluate(config, "x", { userId: "user-1" }, { env }).reason, /^percentage:\d+<100$/);
});
