// Plan rules ignore a trailing billing period (-monthly, -annual) and nothing else.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { MATCHERS } from "../src/matchers.ts";
import type { Flag, Rule } from "../src/types.ts";

const flag: Flag = { key: "x", enabled: true, description: "", rules: [] };
const reason = (values: string[], plan?: string) => MATCHERS.plan({ type: "plan", values } as Rule, plan === undefined ? {} : { plan }, flag).reason;

test("both billing periods are ignored", () => {
  for (const plan of ["plus", "plus-monthly", "plus-annual"]) {
    assert.equal(reason(["plus"], plan), "plan:hit", plan);
  }
  assert.equal(reason(["plus", "business"], "business-annual"), "plan:hit");
});

test("hyphenated plan names keep all their words", () => {
  for (const plan of ["team-pro", "team-pro-monthly", "team-pro-annual"]) {
    assert.equal(reason(["team-pro"], plan), "plan:hit", plan);
  }
  for (const plan of ["team", "team-annual", "team-pro-weekly", "pro"]) {
    assert.equal(reason(["team-pro"], plan), "plan:miss", plan);
  }
  for (const plan of ["team-pro", "team-pro-annual", "team-plus"]) {
    assert.equal(reason(["team"], plan), "plan:miss", plan);
  }
  assert.equal(reason(["team"], "team-monthly"), "plan:hit");
});

test("only a trailing billing period counts", () => {
  for (const plan of ["annual-plus", "plus-annually", "plusannual", "plus-yearly", "free"]) {
    assert.equal(reason(["plus"], plan), "plan:miss", plan);
  }
  assert.equal(reason(["plus"]), "plan:miss");
});

test("the mobile example decides by plan, billing period or not", () => {
  const config = loadConfig(fileURLToPath(new URL("../flags/mobile.json", import.meta.url)));
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "business-annual" }, { env: {} }).reason, "plan:hit");
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "plus-monthly", userId: "u-1" }, { env: {} }).reason, "plan:hit");
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "free-annual", userId: "u-20002" }, { env: {} }).reason, "allowlist:hit");
});
