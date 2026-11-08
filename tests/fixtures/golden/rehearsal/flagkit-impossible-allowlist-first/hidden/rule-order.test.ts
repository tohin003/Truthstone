import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("./order-flags.json", import.meta.url));
const env = {};

function config(rules: unknown[]) {
  return parseConfig({ flags: { "pricing-page": { enabled: true, rules } } });
}

test("the first matching rule in config order decides, even when an allowlist matches later", () => {
  const result = evaluate(
    config([{ type: "country", values: ["DE", "AT"] }, { type: "allowlist", values: ["qa-anna"] }]),
    "pricing-page",
    { userId: "qa-anna", country: "DE" },
    { env },
  );
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "country:hit");
  assert.deepEqual(result.trace.map((step) => [step.rule.type, step.reason]), [["country", "country:hit"]]);
});

test("rules of any type keep their order", () => {
  const rules = [{ type: "plan", values: ["plus"] }, { type: "allowlist", values: ["qa-anna"] }, { type: "percentage", percent: 100 }];
  assert.equal(evaluate(config(rules), "pricing-page", { userId: "qa-anna", plan: "plus" }, { env }).reason, "plan:hit");
  const all = [{ type: "percentage", percent: 100 }, { type: "allowlist", values: ["qa-anna"] }];
  assert.equal(evaluate(config(all), "pricing-page", { userId: "qa-anna" }, { env }).reason.startsWith("percentage:"), true);
});

test("a later allowlist still decides when the earlier rules miss", () => {
  const result = evaluate(
    config([{ type: "country", values: ["DE", "AT"] }, { type: "allowlist", values: ["qa-anna"] }]),
    "pricing-page",
    { userId: "qa-anna", country: "FR" },
    { env },
  );
  assert.equal(result.reason, "allowlist:hit");
  assert.deepEqual(result.trace.map((step) => step.reason), ["country:miss", "allowlist:hit"]);
});

test("an allowlist listed first decides first", () => {
  const result = evaluate(
    config([{ type: "allowlist", values: ["qa-anna"] }, { type: "country", values: ["DE"] }]),
    "pricing-page",
    { userId: "qa-anna", country: "DE" },
    { env },
  );
  assert.equal(result.reason, "allowlist:hit");
  assert.equal(result.trace.length, 1);
});

test("explain shows the rules in config order and which one decided", () => {
  let stdout = "";
  const status = main(["explain", CONFIG, "pricing-page", "--user", "qa-anna", "--country", "DE"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.equal(
    stdout,
    [
      "pricing-page: on (country:hit)",
      "  1. country is DE or AT or CH         hit   country:hit",
      "  2. user is one of 2 allowlisted ids  -     not reached",
      "",
    ].join("\n"),
  );
});
