import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig, RULE_TYPES } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { main } from "../src/cli.ts";

const env = {};
const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));
const config = parseConfig({
  flags: { "staff-only": { enabled: true, rules: [{ type: "email-domain", values: ["acme-staff.com", "acme.io"] }] } },
});

function cli(argv: string[]) {
  let stdout = "";
  const status = main(argv, { stdout: { write: (text: string) => (stdout += text), isTTY: false }, stderr: { write: () => true }, env });
  return { status, stdout };
}

test("email-domain matches an email ending in @<listed domain>, in any case", () => {
  for (const email of ["ann@acme-staff.com", "Ann.Lee@ACME-STAFF.COM", "bo@acme.io"]) {
    const result = evaluate(config, "staff-only", { email }, { env });
    assert.equal(result.enabled, true, email);
    assert.equal(result.reason, "email-domain:hit", email);
  }
});

test("other emails, look-alike domains and a missing email are misses", () => {
  for (const context of [{ email: "ann@example.com" }, { email: "ann@sub.acme-staff.com" }, { email: "ann@acme-staff.com.evil.net" }, { email: "acme-staff.com" }]) {
    const result = evaluate(config, "staff-only", context, { env });
    assert.equal(result.enabled, false, JSON.stringify(context));
    assert.deepEqual(result.trace.map((step) => step.reason), ["email-domain:miss"], JSON.stringify(context));
  }
  assert.equal(evaluate(config, "staff-only", {}, { env }).enabled, false);
});

test("configs validate email-domain rules", () => {
  assert.ok(RULE_TYPES.includes("email-domain"));
  assert.throws(() => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "email-domain", values: ["x.com"], extra: 1 }] } } }), ConfigError);
});

test("the CLI takes --email", () => {
  assert.deepEqual(cli(["eval", storefront, "staff-discounts", "--email", "ann@acme-staff.com"]), { status: 0, stdout: "on (email-domain:hit)\n" });
  assert.equal(cli(["eval", storefront, "staff-discounts", "--email", "ann@example.com"]).stdout, "off (no-match)\n");
});

test("the staff-discounts flag in flags/storefront.json uses the rule", () => {
  const flag = loadConfig(storefront).flags.get("staff-discounts");
  assert.ok(flag !== undefined);
  assert.equal(flag.enabled, true);
  assert.deepEqual(flag.rules, [{ type: "email-domain", values: ["acme-staff.com"] }]);
});

test("explain describes email-domain rules in plain words (e2e suite rule)", () => {
  const { status, stdout } = cli(["explain", storefront, "staff-discounts", "--email", "ann@acme-staff.com"]);
  assert.equal(status, 0);
  assert.match(stdout, /^staff-discounts: on \(email-domain:hit\)\n/);
  assert.doesNotMatch(stdout, /\d\. email-domain rule\s/);
});

test("the README's rules table documents email-domain (e2e suite rule)", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  assert.match(readme, /^\| `email-domain` \|/m);
});

test("the other rule types are unchanged", () => {
  const other = parseConfig({
    flags: { "x-y": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }, { type: "country", values: ["DE"] }] } },
  });
  assert.equal(evaluate(other, "x-y", { userId: "qa-anna" }, { env }).reason, "allowlist:hit");
  assert.equal(evaluate(other, "x-y", { country: "de" }, { env }).reason, "country:hit");
  assert.equal(cli(["eval", storefront, "new-checkout", "--user", "qa-anna"]).stdout, "on (allowlist:hit)\n");
});
