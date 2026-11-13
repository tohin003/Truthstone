import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

function run(argv: string[], env: Record<string, string> = {}) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: (text: string) => (stderr += text) },
    env,
  });
  return { status, stdout, stderr };
}

function oneJsonLine(stdout: string): unknown {
  assert.ok(stdout.endsWith("\n"), JSON.stringify(stdout));
  assert.equal(stdout.trimEnd().split("\n").length, 1, JSON.stringify(stdout));
  return JSON.parse(stdout);
}

test("eval --json prints the flag, its state and the reason as one line of JSON", () => {
  const hit = run(["eval", CONFIG, "new-checkout", "--user", "qa-anna", "--json"]);
  assert.equal(hit.status, 0);
  assert.equal(hit.stderr, "");
  assert.deepEqual(oneJsonLine(hit.stdout), { flag: "new-checkout", enabled: true, reason: "allowlist:hit" });
  const miss = run(["eval", "--json", CONFIG, "search-v2", "--user", "user-1"]);
  assert.deepEqual(oneJsonLine(miss.stdout), { flag: "search-v2", enabled: false, reason: "no-match" });
  assert.deepEqual(oneJsonLine(run(["eval", CONFIG, "gift-cards", "--json"]).stdout), {
    flag: "gift-cards",
    enabled: false,
    reason: "disabled",
  });
});

test("eval --json reports overrides like plain eval", () => {
  const { stdout } = run(["eval", CONFIG, "dark-mode", "--json"], { FLAGKIT_DARK_MODE: "off" });
  assert.deepEqual(oneJsonLine(stdout), { flag: "dark-mode", enabled: false, reason: "override:off" });
});

test("plain eval is unchanged", () => {
  assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "qa-anna"]).stdout, "on (allowlist:hit)\n");
  assert.equal(run(["eval", CONFIG, "dark-mode"]).stdout, "on (everyone)\n");
});

test("explain --json is a usage error", () => {
  const { status, stdout, stderr } = run(["explain", CONFIG, "new-checkout", "--json"]);
  assert.equal(status, 2);
  assert.equal(stdout, "");
  assert.match(stderr, /usage: flagkit <command>/);
});

test("the usage text mentions --json", () => {
  const { status, stdout } = run(["--help"]);
  assert.equal(status, 0);
  assert.match(stdout, /--json/);
});

test("an unknown flag still exits 1 with the reason", () => {
  const { status, stderr } = run(["eval", CONFIG, "nope"]);
  assert.equal(status, 1);
  assert.equal(stderr, `flagkit: unknown flag "nope" in ${CONFIG}\n`);
});
