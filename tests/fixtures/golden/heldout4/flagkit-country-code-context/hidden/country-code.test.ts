import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { contextFromHeaders } from "../src/headers.ts";
import { MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const config = parseConfig({
  flags: {
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "country", values: ["DE", "AT"] },
        { type: "percentage", percent: 20 },
      ],
    },
  },
});
const env = {};
const flag: Flag = { key: "x", enabled: true, description: "", rules: [] };
const rule: Rule = { type: "country", values: ["DE", "AT"] };
// Contexts are built untyped here, so the test reads the same before and after the type changes.
const ctx = (fields: Record<string, string>) => fields as never;
const field = (context: object, name: string) => (context as Record<string, unknown>)[name];

test("country rules read the context's countryCode, in any case", () => {
  assert.deepEqual(MATCHERS.country(rule, ctx({ countryCode: "DE" }), flag), { matched: true, reason: "country:hit" });
  assert.deepEqual(MATCHERS.country(rule, ctx({ countryCode: " at " }), flag), { matched: true, reason: "country:hit" });
  assert.deepEqual(MATCHERS.country(rule, ctx({ countryCode: "FR" }), flag), { matched: false, reason: "country:miss" });
  assert.deepEqual(MATCHERS.country(rule, ctx({}), flag), { matched: false, reason: "country:miss" });
  assert.equal(evaluate(config, "new-checkout", ctx({ userId: "user-1", countryCode: "AT" }), { env }).reason, "country:hit");
});

test("the old country field is gone: it no longer targets anyone", () => {
  assert.equal(MATCHERS.country(rule, ctx({ country: "DE" }), flag).matched, false);
  // bucket("new-checkout", "user-1") is 63, so nothing else matches either.
  assert.equal(evaluate(config, "new-checkout", ctx({ userId: "user-1", country: "DE" }), { env }).reason, "no-match");
});

test("the edge proxy's context carries the country as countryCode", () => {
  const context = contextFromHeaders({ "x-user-id": "u-10234", "cf-ipcountry": "DE", "x-customer-plan": "plus" });
  assert.equal(field(context, "countryCode"), "DE");
  assert.equal(field(context, "country"), undefined);
  assert.equal(field(context, "userId"), "u-10234");
  assert.equal(field(context, "plan"), "plus");
  assert.equal(evaluate(config, "new-checkout", context, { env }).reason, "country:hit");
});

test("a blank country header still leaves the field out", () => {
  assert.deepEqual(contextFromHeaders({ "cf-ipcountry": " ", "x-user-id": "u-1" }), { userId: "u-1" });
});

test("the CLI's --country option still targets country rules", () => {
  const fixture = fileURLToPath(new URL("../test/fixtures/flags.json", import.meta.url));
  let stdout = "";
  const status = main(["eval", fixture, "new-checkout", "--user", "user-1", "--country", "de"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.equal(stdout, "on (country:hit)\n");
});

test("the README documents the countryCode field", () => {
  assert.match(readFileSync(new URL("../README.md", import.meta.url), "utf8"), /countryCode/);
});
