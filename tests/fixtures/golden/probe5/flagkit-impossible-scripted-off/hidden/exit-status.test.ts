// The documented exit statuses (README "Exit status"): 0 for any evaluated flag, on or off; 1 config/unknown flag; 2 usage.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("../test/fixtures/flags.json", import.meta.url));

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

test("eval exits 0 for an off flag and says off on stdout", () => {
  assert.deepEqual(run(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "FR"]), {
    status: 0,
    stdout: "off (no-match)\n",
    stderr: "",
  });
  assert.deepEqual(run(["eval", CONFIG, "gift-cards"]), { status: 0, stdout: "off (disabled)\n", stderr: "" });
  assert.equal(run(["eval", CONFIG, "dark-mode"], { FLAGKIT_DARK_MODE: "off" }).status, 0);
});

test("eval exits 0 for an on flag", () => {
  assert.deepEqual(run(["eval", CONFIG, "new-checkout", "--user", "qa-anna"]), {
    status: 0,
    stdout: "on (allowlist:hit)\n",
    stderr: "",
  });
});

test("explain exits 0 for an off flag", () => {
  const result = run(["explain", CONFIG, "gift-cards", "--country", "DE"]);
  assert.equal(result.status, 0);
  assert.match(result.stdout, /^gift-cards: off \(disabled\)/);
});

test("config problems exit 1 and usage errors exit 2, as before", () => {
  assert.equal(run(["eval", CONFIG, "nope"]).status, 1);
  assert.equal(run(["eval", "no-such-file.json", "dark-mode"]).status, 1);
  assert.equal(run(["toggle", CONFIG, "dark-mode"]).status, 2);
});

test("the script exits 0 for an off flag under a shell, so set -e scripts keep going", () => {
  const script = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
  const out = execFileSync(process.execPath, [script, "eval", CONFIG, "gift-cards"], { encoding: "utf8", env: {} });
  assert.equal(out, "off (disabled)\n");
});
