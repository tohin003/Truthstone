// The rename one-tap-reorder -> quick-reorder, including the override variables derived from the key.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { envName } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

const root = new URL("../", import.meta.url);
const mobile = () => loadConfig(fileURLToPath(new URL("flags/mobile.json", root)));

function envFile(name: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of readFileSync(new URL(`deploy/${name}`, root), "utf8").split("\n")) {
    const text = line.trim();
    const eq = text.indexOf("=");
    if (text && !text.startsWith("#") && eq > 0) {
      env[text.slice(0, eq).trim()] = text.slice(eq + 1).trim();
    }
  }
  return env;
}

function flagVariables(): Set<string> {
  const names = new Set<string>();
  for (const file of readdirSync(new URL("flags/", root)).filter((name) => name.endsWith(".json"))) {
    for (const key of loadConfig(fileURLToPath(new URL(`flags/${file}`, root))).flags.keys()) {
      names.add(envName(key));
    }
  }
  return names;
}

test("the flag is quick-reorder now, with the same rules", () => {
  const config = mobile();
  assert.equal(config.flags.has("one-tap-reorder"), false);
  const flag = config.flags.get("quick-reorder");
  assert.ok(flag, "quick-reorder is defined");
  assert.equal(flag.enabled, true);
  assert.deepEqual(flag.rules, [
    { type: "plan", values: ["plus", "business"] },
    { type: "allowlist", values: ["u-20001", "u-20002"] },
  ]);
  assert.equal(evaluate(config, "quick-reorder", { plan: "plus" }, { env: {} }).reason, "plan:hit");
  assert.equal(evaluate(config, "quick-reorder", { userId: "u-20002" }, { env: {} }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "plus" }, { env: {} }).reason, "unknown-flag");
});

test("the kiosks still force reordering on", () => {
  const result = evaluate(mobile(), "quick-reorder", { plan: "free" }, { env: envFile("kiosk.env") });
  assert.deepEqual([result.enabled, result.reason], [true, "override:on"]);
});

test("every FLAGKIT_ variable in the deploy environments names a flag", () => {
  const known = flagVariables();
  for (const file of readdirSync(new URL("deploy/", root)).filter((name) => name.endsWith(".env"))) {
    for (const variable of Object.keys(envFile(file)).filter((name) => name.startsWith("FLAGKIT_"))) {
      assert.ok(known.has(variable), `${file}: ${variable} matches no flag`);
    }
  }
});

test("every FLAGKIT_ variable the runbooks tell on-call to set names a flag", () => {
  const known = flagVariables();
  const runbooks = readdirSync(new URL("docs/runbooks/", root)).filter((name) => name.endsWith(".md"));
  let seen = 0;
  for (const file of runbooks) {
    const text = readFileSync(new URL(`docs/runbooks/${file}`, root), "utf8");
    for (const [variable] of text.matchAll(/FLAGKIT_[A-Z0-9_]+/g)) {
      seen += 1;
      assert.ok(known.has(variable), `${file}: ${variable} matches no flag`);
    }
  }
  assert.ok(seen >= 2);
});

test("the mobile API's offline-cart override is untouched", () => {
  const result = evaluate(mobile(), "offline-cart", { userId: "u-20001" }, { env: envFile("mobile-api.env") });
  assert.deepEqual([result.enabled, result.reason], [false, "override:off"]);
});
