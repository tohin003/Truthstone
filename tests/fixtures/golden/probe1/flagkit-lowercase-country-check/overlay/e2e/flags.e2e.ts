// End-to-end: every example config in flags/ through the CLI, the way the deploy scripts use them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { loadConfig } from "../src/config.ts";

const FLAGS = fileURLToPath(new URL("../flags/", import.meta.url));

function evalFlag(file: string, flag: string, ...options: string[]): string {
  let stdout = "";
  let stderr = "";
  const status = main(["eval", FLAGS + file, flag, ...options], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: (text: string) => (stderr += text) },
    env: {},
  });
  assert.equal(status, 0, stderr);
  return stdout.trim();
}

test("every example config in flags/ loads", () => {
  const files = readdirSync(FLAGS).filter((name) => name.endsWith(".json"));
  assert.ok(files.length >= 3);
  for (const file of files) {
    assert.doesNotThrow(() => loadConfig(FLAGS + file), file);
  }
});

test("storefront flags", () => {
  assert.equal(evalFlag("storefront.json", "new-checkout", "--user", "qa-anna"), "on (allowlist:hit)");
  assert.equal(evalFlag("storefront.json", "new-checkout", "--user", "user-1", "--country", "CH"), "on (country:hit)");
  assert.equal(evalFlag("storefront.json", "gift-cards"), "off (disabled)");
});

test("mobile flags", () => {
  assert.equal(evalFlag("mobile.json", "one-tap-reorder", "--plan", "plus"), "on (plan:hit)");
  assert.equal(evalFlag("mobile.json", "offline-cart", "--user", "u-20001"), "on (percentage:0<50)");
});

test("marketing flags", () => {
  assert.equal(evalFlag("marketing.json", "eu-banner", "--country", "DE"), "on (country:hit)");
  assert.equal(evalFlag("marketing.json", "eu-banner", "--country", "nl"), "on (country:hit)");
  assert.equal(evalFlag("marketing.json", "eu-banner", "--country", "FR"), "off (no-match)");
  assert.equal(evalFlag("marketing.json", "spring-sale", "--plan", "plus"), "on (plan:hit)");
});
