import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const CONFIG = fileURLToPath(new URL("./segments-config.json", import.meta.url));
const env = {};

function config() {
  return {
    segments: { "beta-testers": ["u-1", "u-2"], staff: ["s-9"] },
    flags: {
      "new-search": { enabled: true, rules: [{ type: "segment", name: "beta-testers" }] as object[] },
      "admin-tools": {
        enabled: true,
        rules: [
          { type: "country", values: ["DE"] },
          { type: "segment", name: "staff" },
        ] as object[],
      },
    },
  };
}

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

const isConfigError = (...needles: string[]) => (error: unknown) =>
  error instanceof ConfigError && needles.every((needle) => error.message.includes(needle));

test("a config with segments and segment rules parses, from an object or a file", () => {
  assert.doesNotThrow(() => parseConfig(config()));
  assert.doesNotThrow(() => loadConfig(CONFIG));
});

test("a segment rule matches the segment's members", () => {
  const result = evaluate(parseConfig(config()), "new-search", { userId: "u-2" }, { env });
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "segment:hit");
});

test("users outside the segment, and anonymous users, miss", () => {
  const parsed = parseConfig(config());
  const outsider = evaluate(parsed, "new-search", { userId: "u-3" }, { env });
  assert.equal(outsider.enabled, false);
  assert.deepEqual(outsider.trace.map((step) => step.reason), ["segment:miss"]);
  assert.equal(evaluate(parsed, "new-search", {}, { env }).enabled, false);
  assert.equal(evaluate(parsed, "new-search", { userId: "s-9" }, { env }).enabled, false);
});

test("segment rules combine with the other rules, first match wins", () => {
  const parsed = parseConfig(config());
  assert.equal(evaluate(parsed, "admin-tools", { userId: "s-9", country: "FR" }, { env }).reason, "segment:hit");
  assert.equal(evaluate(parsed, "admin-tools", { userId: "u-1", country: "DE" }, { env }).reason, "country:hit");
  assert.equal(evaluate(parsed, "admin-tools", { userId: "u-1", country: "FR" }, { env }).reason, "no-match");
});

test("configs without segments still work", () => {
  const parsed = parseConfig({ flags: { "dark-mode": { enabled: true }, beta: { enabled: true, rules: [{ type: "allowlist", values: ["u-1"] }] } } });
  assert.equal(evaluate(parsed, "dark-mode", {}, { env }).reason, "everyone");
  assert.equal(evaluate(parsed, "beta", { userId: "u-1" }, { env }).reason, "allowlist:hit");
});

test("segments must be a map of user-id lists", () => {
  assert.throws(() => parseConfig({ segments: ["u-1"], flags: {} }), ConfigError);
  assert.throws(() => parseConfig({ segments: { beta: "u-1" }, flags: {} }), ConfigError);
  assert.throws(() => parseConfig({ segments: { beta: [1, 2] }, flags: {} }), ConfigError);
});

test("a segment rule naming an undefined segment is a config error naming flag and segment", () => {
  const typo = config();
  typo.flags["new-search"].rules = [{ type: "segment", name: "beta-tester" }];
  assert.throws(() => parseConfig(typo), isConfigError("new-search", "beta-tester"));

  const noSegments = { flags: { "ops-panel": { enabled: true, rules: [{ type: "segment", name: "staff" }] } } };
  assert.throws(() => parseConfig(noSegments), isConfigError("ops-panel", "staff"));
});

test("a segment rule needs a name", () => {
  const nameless = config();
  nameless.flags["new-search"].rules = [{ type: "segment" }];
  assert.throws(() => parseConfig(nameless), isConfigError("new-search"));
});

test("explain names the segment of a segment rule that matched", () => {
  const { status, stdout } = cli(["explain", CONFIG, "new-search", "--user", "u-1"]);
  assert.equal(status, 0);
  assert.match(stdout, /^new-search: on \(segment:hit\)$/m);
  assert.match(stdout, /beta-testers/);
});

test("explain names the segment of a segment rule that was evaluated after others", () => {
  const { status, stdout } = cli(["explain", CONFIG, "admin-tools", "--user", "s-9", "--country", "FR"]);
  assert.equal(status, 0);
  const segmentLine = stdout.split("\n").find((line) => line.trimStart().startsWith("2."));
  assert.ok(segmentLine, stdout);
  assert.match(segmentLine, /staff/);
});

test("unknown top-level keys are still rejected", () => {
  assert.throws(() => parseConfig({ segmentz: {}, flags: {} }), isConfigError("segmentz"));
});
