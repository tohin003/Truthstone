// A flag defined twice in a config file is rejected by loadConfig, naming the file and the flag; valid configs still load.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";

const here = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
const repo = (path: string) => fileURLToPath(new URL(`../${path}`, import.meta.url));

test("a flag defined twice is rejected, naming the file and the flag", () => {
  assert.throws(
    () => loadConfig(repo("test/fixtures/duplicate-flag.json")),
    (error: unknown) => error instanceof ConfigError && /duplicate-flag\.json: flag "new-checkout" is defined twice/.test(error.message),
  );
  assert.throws(
    () => loadConfig(here("twice-last.json")),
    (error: unknown) => error instanceof ConfigError && /twice-last\.json: flag "dark-mode" is defined twice/.test(error.message),
  );
});

test("fields repeated across different flags and rules are not duplicates", () => {
  const config = loadConfig(here("shared-fields.json"));
  assert.deepEqual([...config.flags.keys()], ["one-tap-reorder", "offline-cart"]);
  assert.equal(config.flags.get("offline-cart")?.rules.length, 2);
});

test("the example configs and the test fixture still load", () => {
  assert.ok(loadConfig(repo("flags/storefront.json")).flags.size > 0);
  assert.ok(loadConfig(repo("flags/mobile.json")).flags.size > 0);
  assert.deepEqual([...loadConfig(repo("test/fixtures/flags.json")).flags.keys()], ["new-checkout", "gift-cards", "dark-mode"]);
});

test("the other load errors are unchanged", () => {
  assert.throws(() => loadConfig(repo("test/fixtures/broken.json")), /broken\.json is not valid JSON/);
  assert.throws(() => loadConfig(repo("test/fixtures/bad-rule.json")), /flag "beta-banner": rule 1: unknown rule type "weekday"/);
});
