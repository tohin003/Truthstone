import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { describeRule, explain, main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "beta-search": {
      enabled: true,
      rules: [
        { type: "country", values: ["NL"] },
        { type: "allowlist", values: ["qa-anna", "qa-ben", "u-31007"] },
      ],
    },
    "beta-invoices": {
      enabled: true,
      rules: [
        { type: "plan", values: ["business"] },
        { type: "country", values: ["NL", "BE", "LU"] },
        { type: "percentage", percent: 5 },
      ],
    },
    "beta-maps": { enabled: false, rules: [{ type: "plan", values: ["plus"] }, { type: "country", values: ["DE", "AT", "CH"] }] },
  },
});

function lines(flagKey: string, context: Record<string, string>, env: Record<string, string> = {}): string[] {
  const flag = config.flags.get(flagKey);
  assert.ok(flag);
  return explain(flag, evaluate(config, flagKey, context, { env })).trimEnd().split("\n");
}

/** The column where each rule line's verdict starts: after "  N. ", the padded description and two spaces. */
function verdictColumns(output: string[]): number[] {
  return output.filter((line) => /^ {2}\d+\. /.test(line)).map((line) => line.search(/ {2}(hit|miss|-) /) + 2);
}

test("the verdicts line up when the deciding rule is the shortest", () => {
  const output = lines("beta-search", { country: "NL" });
  assert.deepEqual(output, [
    "beta-search: on (country:hit)",
    "  1. country is NL                     hit   country:hit",
    "  2. user is one of 3 allowlisted ids  -     not reached",
  ]);
});

test("the column is as wide as the longest description of every rule, reached or not", () => {
  const width = Math.max(...(config.flags.get("beta-invoices")?.rules ?? []).map((rule) => describeRule(rule).length));
  for (const context of [{ plan: "business" }, { country: "BE" }, { userId: "user-1" }, {}]) {
    const columns = verdictColumns(lines("beta-invoices", context));
    assert.deepEqual(columns, [5 + width + 2, 5 + width + 2, 5 + width + 2], JSON.stringify(context));
  }
});

test("disabled and overridden flags list their rules in the same columns", () => {
  const disabled = lines("beta-maps", { country: "DE" });
  assert.equal(disabled[1], "  (rules not evaluated: disabled)");
  assert.deepEqual(disabled.slice(2), [
    "  1. plan is plus               -     not reached",
    "  2. country is DE or AT or CH  -     not reached",
  ]);
  const overridden = lines("beta-search", { country: "NL" }, { FLAGKIT_BETA_SEARCH: "off" });
  assert.equal(overridden[0], "beta-search: off (override:off)");
  assert.deepEqual(verdictColumns(overridden), [39, 39]);
});

test("the command line prints the same, and bolds the deciding line on a terminal", () => {
  const fixture = fileURLToPath(new URL("../test/fixtures/beta.json", import.meta.url));
  let stdout = "";
  const status = main(["explain", fixture, "beta-search", "--country", "NL"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: true },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.match(stdout, /\u001b\[1m {2}1\. country is NL {21}hit {3}country:hit\u001b\[0m/);
  assert.match(stdout, /\n {2}2\. user is one of 3 allowlisted ids {2}- {5}not reached\n/);
});

test("eval output is unchanged", () => {
  const flag = config.flags.get("beta-search");
  assert.ok(flag);
  assert.equal(evaluate(config, "beta-search", { country: "NL" }, { env: {} }).reason, "country:hit");
});
