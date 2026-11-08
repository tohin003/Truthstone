import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("./fixtures/flags.json", import.meta.url));
const BETA = fileURLToPath(new URL("./fixtures/beta.json", import.meta.url));

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

test("eval prints the state and the reason", () => {
  assert.deepEqual(run(["eval", CONFIG, "new-checkout", "--user", "qa-anna"]), {
    status: 0,
    stdout: "on (allowlist:hit)\n",
    stderr: "",
  });
  assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "DE"]).stdout, "on (country:hit)\n");
  assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "FR"]).stdout, "off (no-match)\n");
  assert.equal(run(["eval", CONFIG, "dark-mode"]).stdout, "on (everyone)\n");
});

test("eval honours env overrides", () => {
  const { stdout } = run(["eval", CONFIG, "new-checkout", "--user", "qa-anna"], { env: { FLAGKIT_NEW_CHECKOUT: "off" } });
  assert.equal(stdout, "off (override:off)\n");
});

test("explain shows every rule and which one decided", () => {
  const { status, stdout } = run(["explain", CONFIG, "new-checkout", "--user", "user-1", "--country", "de"]);
  assert.equal(status, 0);
  assert.equal(
    stdout,
    [
      "new-checkout: on (country:hit)",
      "  1. user is one of 2 allowlisted ids  miss  allowlist:miss",
      "  2. country is DE or AT               hit   country:hit",
      "  3. user's bucket is below 20         -     not reached",
      "",
    ].join("\n"),
  );
});

test("explain lines up the verdicts even when the longest rule was not reached", () => {
  assert.equal(
    run(["explain", BETA, "beta-search", "--country", "NL"]).stdout,
    [
      "beta-search: on (country:hit)",
      "  1. country is NL                     hit   country:hit",
      "  2. user is one of 3 allowlisted ids  -     not reached",
      "",
    ].join("\n"),
  );
});

test("explain says when no rule was evaluated", () => {
  assert.equal(
    run(["explain", CONFIG, "gift-cards", "--country", "DE"]).stdout,
    "gift-cards: off (disabled)\n  (rules not evaluated: disabled)\n  1. country is DE  -     not reached\n",
  );
  assert.equal(run(["explain", CONFIG, "dark-mode"]).stdout, "dark-mode: on (everyone)\n");
});

test("explain highlights the deciding rule on a terminal, unless NO_COLOR is set", () => {
  const argv = ["explain", CONFIG, "new-checkout", "--user", "qa-anna"];
  assert.match(run(argv, { isTTY: true }).stdout, /\u001b\[1m {2}1\. user is one of 2 allowlisted ids {2}hit {3}allowlist:hit\u001b\[0m/);
  assert.doesNotMatch(run(argv, { isTTY: true, env: { NO_COLOR: "1" } }).stdout, /\u001b/);
  assert.doesNotMatch(run(argv, { isTTY: false }).stdout, /\u001b/);
});

test("an unknown flag or a bad config exits 1 with the reason", () => {
  const unknown = run(["eval", CONFIG, "nope"]);
  assert.equal(unknown.status, 1);
  assert.equal(unknown.stderr, `flagkit: unknown flag "nope" in ${CONFIG}\n`);
  const missing = run(["eval", "no-such-file.json", "dark-mode"]);
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /^flagkit: cannot read no-such-file\.json: ENOENT$/m);
});

test("usage errors exit 2 and print the usage", () => {
  for (const argv of [[], ["toggle", CONFIG, "dark-mode"], ["eval", CONFIG], ["eval", CONFIG, "dark-mode", "--colour"]]) {
    const { status, stderr } = run(argv);
    assert.equal(status, 2, argv.join(" "));
    assert.match(stderr, /usage: flagkit <command>/);
  }
});

test("--help prints the usage", () => {
  const { status, stdout } = run(["--help"]);
  assert.equal(status, 0);
  assert.match(stdout, /^usage: flagkit <command> <config\.json> <flag>/);
});

test("the script runs from the command line", () => {
  const script = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
  const out = execFileSync(process.execPath, [script, "eval", CONFIG, "dark-mode"], { encoding: "utf8", env: {} });
  assert.equal(out, "on (everyone)\n");
});
