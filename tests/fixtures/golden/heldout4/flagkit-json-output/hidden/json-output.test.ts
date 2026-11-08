import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const CONFIG = fileURLToPath(new URL("../test/fixtures/flags.json", import.meta.url));

function run(argv: string[], options: { isTTY?: boolean; env?: Record<string, string> } = {}) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: options.isTTY ?? false },
    stderr: { write: (text: string) => (stderr += text) },
    env: options.env ?? {},
  });
  return { status, stdout, stderr };
}

const cases: Array<[string, Record<string, string>, string[]]> = [
  ["new-checkout", { userId: "qa-anna" }, ["--user", "qa-anna"]],
  ["new-checkout", { userId: "user-1", country: "DE" }, ["--user", "user-1", "--country", "DE"]],
  ["new-checkout", { userId: "user-1", country: "FR" }, ["--user", "user-1", "--country", "FR"]],
  ["new-checkout", { userId: "user-3", country: "FR" }, ["--user", "user-3", "--country", "FR"]],
  ["gift-cards", { country: "DE" }, ["--country", "DE"]],
  ["dark-mode", {}, []],
];

for (const command of ["eval", "explain"]) {
  test(`${command} --json prints exactly the evaluation, on one line`, () => {
    const config = loadConfig(CONFIG);
    for (const [flag, context, options] of cases) {
      const { status, stdout, stderr } = run([command, CONFIG, flag, ...options, "--json"]);
      assert.equal(status, 0, `${flag} ${options.join(" ")}`);
      assert.equal(stderr, "");
      assert.ok(stdout.endsWith("\n") && stdout.indexOf("\n") === stdout.length - 1, stdout);
      assert.deepEqual(JSON.parse(stdout), evaluate(config, flag, context, { env: {} }));
    }
  });
}

test("--json reports an env override like evaluate does", () => {
  const { stdout } = run(["eval", CONFIG, "new-checkout", "--user", "qa-anna", "--json"], { env: { FLAGKIT_NEW_CHECKOUT: "off" } });
  assert.deepEqual(JSON.parse(stdout), { flag: "new-checkout", enabled: false, reason: "override:off", trace: [] });
});

test("JSON output has no colour codes, even on a terminal", () => {
  const { stdout } = run(["explain", CONFIG, "new-checkout", "--user", "qa-anna", "--json"], { isTTY: true });
  assert.doesNotMatch(stdout, /\u001b/);
  assert.equal(JSON.parse(stdout).reason, "allowlist:hit");
});

test("the option can come anywhere among the options", () => {
  const { stdout } = run(["eval", "--json", CONFIG, "dark-mode"]);
  assert.deepEqual(JSON.parse(stdout), { flag: "dark-mode", enabled: true, reason: "everyone", trace: [] });
});

test("without --json the text output is unchanged", () => {
  assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "qa-anna"]).stdout, "on (allowlist:hit)\n");
  assert.equal(run(["explain", CONFIG, "dark-mode"]).stdout, "dark-mode: on (everyone)\n");
});

test("errors and exit statuses stay as they were", () => {
  const unknown = run(["eval", CONFIG, "nope", "--json"]);
  assert.equal(unknown.status, 1);
  assert.equal(unknown.stdout, "");
  assert.equal(unknown.stderr, `flagkit: unknown flag "nope" in ${CONFIG}\n`);
  const usage = run(["eval", CONFIG, "--json"]);
  assert.equal(usage.status, 2);
  assert.match(usage.stderr, /usage: flagkit <command>/);
});

test("--help lists the option", () => {
  const { status, stdout } = run(["--help"]);
  assert.equal(status, 0);
  assert.match(stdout, /--json/);
});
