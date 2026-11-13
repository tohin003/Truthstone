// Every QA account gets new-checkout through the allowlist, via `qa-*`, and plain ids still match exactly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const STOREFRONT = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("every QA account, old and new, gets new-checkout from the allowlist", () => {
  const config = loadConfig(STOREFRONT);
  for (const userId of ["qa-anna", "qa-ben", "qa-chris", "qa-dana", "qa-zoe-2"]) {
    const result = evaluate(config, "new-checkout", { userId }, { env: {} });
    assert.equal(result.enabled, true, userId);
    assert.equal(result.reason, "allowlist:hit", userId);
  }
});

test("u-10234 keeps its place on the allowlist and other users do not hit it", () => {
  const config = loadConfig(STOREFRONT);
  assert.equal(evaluate(config, "new-checkout", { userId: "u-10234" }, { env: {} }).reason, "allowlist:hit");
  for (const userId of ["user-1", "aqa-1", "qa"]) {
    assert.notEqual(evaluate(config, "new-checkout", { userId }, { env: {} }).reason, "allowlist:hit", userId);
  }
});

test("the storefront allowlist uses the wildcard instead of listing QA ids", () => {
  const raw = JSON.parse(readFileSync(STOREFRONT, "utf8"));
  const allowlist = raw.flags["new-checkout"].rules.find((rule: { type: string }) => rule.type === "allowlist");
  assert.ok(allowlist.values.includes("qa-*"));
  assert.ok(allowlist.values.includes("u-10234"));
});

test("a value with * matches any id with that prefix; a value without * matches only itself", () => {
  const config = parseConfig({
    flags: { "x-y": { enabled: true, rules: [{ type: "allowlist", values: ["ops-*", "anna"] }] } },
  });
  const reason = (userId: string) => evaluate(config, "x-y", { userId }, { env: {} }).reason;
  assert.equal(reason("ops-1"), "allowlist:hit");
  assert.equal(reason("ops-team-berlin"), "allowlist:hit");
  assert.equal(reason("anna"), "allowlist:hit");
  assert.equal(reason("anna2"), "no-match");
  assert.equal(reason("devops-1"), "no-match");
  assert.equal(evaluate(config, "x-y", {}, { env: {} }).reason, "no-match");
});
