import { test } from "node:test";
import assert from "node:assert/strict";
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

test("eval exits 0 for a flag that is off", () => {
  assert.deepEqual(run(["eval", CONFIG, "gift-cards"]), { status: 0, stdout: "off (disabled)\n", stderr: "" });
  assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "FR"]).status, 0);
  assert.equal(run(["eval", CONFIG, "dark-mode"], { FLAGKIT_DARK_MODE: "off" }).status, 0);
});

test("explain exits 0 for a flag that is off", () => {
  assert.equal(run(["explain", CONFIG, "gift-cards"]).status, 0);
});

test("on flags still exit 0, config problems 1 and usage errors 2", () => {
  assert.equal(run(["eval", CONFIG, "dark-mode"]).status, 0);
  assert.equal(run(["eval", CONFIG, "no-such-flag"]).status, 1);
  assert.equal(run(["eval", CONFIG]).status, 2);
});
