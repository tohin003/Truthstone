import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";

// JSON.parse keeps the last of two equal keys without a word, so a flag pasted twice into a
// config silently replaces the first one. loadConfig must reject repeated keys (README "Config").
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

function rejects(path: string, message: RegExp) {
  assert.throws(
    () => loadConfig(path),
    (error: unknown) => error instanceof ConfigError && message.test(error.message) && error.message.includes(path),
  );
}

test("a flag defined twice is rejected, naming the flag", () => {
  rejects(fixture("duplicate-flag.json"), /duplicate flag "new-checkout"/);
});

test("a field given twice in one flag is rejected, naming the flag and the field", () => {
  rejects(fixture("duplicate-field.json"), /flag "gift-cards": duplicate field "enabled"/);
});

test("a field given twice in one rule is rejected, naming the flag, the rule and the field", () => {
  rejects(fixture("duplicate-rule-field.json"), /flag "search-v2": rule 1: duplicate field "percent"/);
});

test("equal keys in different objects, and key-like text inside strings, are fine", () => {
  const config = loadConfig(fixture("lookalikes.json"));
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "dark-mode"]);
  assert.equal(config.flags.get("new-checkout")?.rules.length, 2);
});

test("the shipped configs have no repeated keys", () => {
  const dir = fileURLToPath(new URL("../flags/", import.meta.url));
  for (const name of readdirSync(dir).filter((file) => file.endsWith(".json"))) {
    loadConfig(dir + name);
  }
});
