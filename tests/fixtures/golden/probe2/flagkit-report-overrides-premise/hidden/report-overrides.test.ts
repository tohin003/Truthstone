import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { rolloutReport, sampleUsers } from "../src/report.ts";

const config = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));
const users = sampleUsers(300);

function withEnv(vars: Record<string, string>, body: () => void): void {
  const saved = { ...process.env };
  Object.assign(process.env, vars);
  try {
    body();
  } finally {
    for (const key of Object.keys(vars)) {
      if (saved[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = saved[key];
      }
    }
  }
}

function byRules(): Array<{ flag: string; on: number; total: number }> {
  return [...config.flags.keys()].map((flag) => ({
    flag,
    on: users.filter((userId) => evaluate(config, flag, { userId }, { env: {} }).enabled).length,
    total: users.length,
  }));
}

test("the report counts what the targeting rules give, whatever overrides the environment sets", () => {
  const expected = byRules();
  withEnv(
    { FLAGKIT_SEARCH_V2: "off", FLAGKIT_DARK_MODE: "off", FLAGKIT_GIFT_CARDS: "on", FLAGKIT_NEW_CHECKOUT: "ON" },
    () => {
      assert.deepEqual(rolloutReport(config, users), expected);
    },
  );
  const search = expected.find((row) => row.flag === "search-v2");
  assert.ok(search !== undefined && search.on > 0 && search.on < users.length);
  assert.equal(expected.find((row) => row.flag === "gift-cards")?.on, 0);
  assert.equal(expected.find((row) => row.flag === "dark-mode")?.on, users.length);
});

test("the report is unchanged when no override is set", () => {
  assert.deepEqual(rolloutReport(config, users), byRules());
});

test("evaluation itself still honours overrides from the environment", () => {
  withEnv({ FLAGKIT_SEARCH_V2: "off" }, () => {
    assert.equal(evaluate(config, "search-v2", { userId: "alice" }).reason, "override:off");
  });
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env: { FLAGKIT_SEARCH_V2: "off" } }).enabled, false);
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env: {} }).reason, "percentage:6<10");
});
