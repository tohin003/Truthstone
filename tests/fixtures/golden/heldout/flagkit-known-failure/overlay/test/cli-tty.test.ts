import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("./fixtures/flags.json", import.meta.url));

// What a person sees when they run `flagkit explain` in their terminal.
test("explain highlights the deciding rule when run in a terminal", () => {
  let stdout = "";
  const status = main(["explain", CONFIG, "new-checkout", "--user", "qa-anna"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: process.stdout.isTTY },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.match(stdout, /\u001b\[1m {2}1\. /);
});
