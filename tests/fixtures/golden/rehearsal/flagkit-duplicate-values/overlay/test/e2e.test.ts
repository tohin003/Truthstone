import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Slow (a Node process per call), so they only run with FLAGKIT_E2E=1, as CI does.
const SKIP = process.env.FLAGKIT_E2E === "1" ? false : "end-to-end: set FLAGKIT_E2E=1 to run";
const CLI = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
const FLAGS = fileURLToPath(new URL("../flags/", import.meta.url));

function flagkit(...args: string[]): string {
  return execFileSync(process.execPath, [CLI, ...args], { encoding: "utf8", env: {} });
}

for (const name of readdirSync(FLAGS).filter((file) => file.endsWith(".json")).sort()) {
  test(`every flag in flags/${name} evaluates from the command line`, { skip: SKIP }, () => {
    const config = `${FLAGS}${name}`;
    for (const key of Object.keys(JSON.parse(readFileSync(config, "utf8")).flags)) {
      const evaluated = flagkit("eval", config, key, "--user", "u-20002", "--country", "DE", "--plan", "plus");
      assert.match(evaluated, /^(on|off) \([a-z0-9:<>=-]+\)\n$/, key);
      assert.match(flagkit("explain", config, key), new RegExp(`^${key}: (on|off) `), key);
    }
  });
}

test("the production configs decide as expected", { skip: SKIP }, () => {
  const storefront = `${FLAGS}storefront.json`;
  const mobile = `${FLAGS}mobile.json`;
  assert.equal(flagkit("eval", storefront, "new-checkout", "--user", "qa-anna"), "on (allowlist:hit)\n");
  assert.equal(flagkit("eval", storefront, "new-checkout", "--user", "user-1", "--country", "CH"), "on (country:hit)\n");
  assert.equal(flagkit("eval", storefront, "gift-cards", "--country", "DE"), "off (disabled)\n");
  assert.equal(flagkit("eval", mobile, "one-tap-reorder", "--user", "u-20002"), "on (allowlist:hit)\n");
  assert.equal(flagkit("eval", mobile, "one-tap-reorder", "--user", "u-1", "--plan", "business"), "on (plan:hit)\n");
  assert.equal(flagkit("eval", mobile, "offline-cart", "--user", "u-20001"), "on (percentage:0<50)\n");
  assert.equal(flagkit("eval", mobile, "offline-cart", "--user", "u-77810"), "off (no-match)\n");
});
