import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("../test/fixtures/flags.json", import.meta.url));
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const BOLD_LINE = /\u001b\[1m {2}1\. user is one of 2 allowlisted ids {2}hit {3}allowlist:hit\u001b\[0m/;

function explain(isTTY: boolean, env: Record<string, string>): string {
  let stdout = "";
  main(["explain", CONFIG, "new-checkout", "--user", "qa-anna"], {
    stdout: { write: (text: string) => (stdout += text), isTTY },
    stderr: { write: () => true },
    env,
  });
  return stdout;
}

test("FORCE_COLOR=1 makes explain highlight the deciding rule when stdout is not a terminal", () => {
  const output = execFileSync(process.execPath, ["src/cli.ts", "explain", CONFIG, "new-checkout", "--user", "qa-anna"], {
    cwd: ROOT,
    env: { PATH: process.env.PATH ?? "", FORCE_COLOR: "1" },
    encoding: "utf8",
  });
  assert.match(output, BOLD_LINE);
});

test("without FORCE_COLOR, explain off a terminal stays plain and on a terminal stays bold", () => {
  assert.doesNotMatch(explain(false, {}), /\u001b/);
  assert.match(explain(true, {}), BOLD_LINE);
  assert.doesNotMatch(explain(true, { NO_COLOR: "1" }), /\u001b/);
});

test("the rollout report prints the deciding rule in bold into a captured log", () => {
  const output = execFileSync("sh", ["scripts/rollout-report.sh"], {
    cwd: ROOT,
    env: { PATH: process.env.PATH ?? "" },
    encoding: "utf8",
  });
  assert.match(output, /\u001b\[1m {2}2\. country is DE or AT or CH +hit {3}country:hit\u001b\[0m/);
  assert.match(output, /^search-v2: off \(no-match\)$/m);
});
