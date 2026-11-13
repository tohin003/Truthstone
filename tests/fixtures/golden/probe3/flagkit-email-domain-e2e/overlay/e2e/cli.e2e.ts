import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig, RULE_TYPES } from "../src/config.ts";

// End-to-end: the real CLI, run as a separate process, against every example config in flags/.
const cli = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
const configs = readdirSync(new URL("../flags/", import.meta.url))
  .filter((name) => name.endsWith(".json"))
  .map((name) => fileURLToPath(new URL(`../flags/${name}`, import.meta.url)));

function flagkit(args: string[]): string {
  return execFileSync(process.execPath, [cli, ...args], { encoding: "utf8", env: {} });
}

test("there are example configs to check", () => {
  assert.ok(configs.length >= 2, configs.join(", "));
});

test("every flag of every example config evaluates from the command line", () => {
  for (const path of configs) {
    for (const key of loadConfig(path).flags.keys()) {
      assert.match(flagkit(["eval", path, key, "--user", "e2e-user"]), /^(on|off) \([^)]+\)\n$/, `${path}: ${key}`);
    }
  }
});

test("explain describes every rule of the example configs in plain words", () => {
  for (const path of configs) {
    for (const [key, flag] of loadConfig(path).flags) {
      const out = flagkit(["explain", path, key, "--user", "e2e-user"]);
      assert.ok(out.startsWith(`${key}: `), out);
      for (const rule of flag.rules) {
        // describeRule's fallback ("<type> rule") means explain has no description for the type
        assert.doesNotMatch(out, new RegExp(`\\d\\. ${rule.type} rule\\s`), `${key}: no description for ${rule.type} rules`);
      }
    }
  }
});

test("every rule type is documented in the README's rules table", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  for (const type of RULE_TYPES) {
    assert.match(readme, new RegExp(`^\\| \`${type}\` \\|`, "m"), `${type} is missing from the README's rules table`);
  }
});
