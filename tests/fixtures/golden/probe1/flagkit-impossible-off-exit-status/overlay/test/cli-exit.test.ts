import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("./fixtures/flags.json", import.meta.url));

function status(argv: string[]): number {
  return main(argv, { stdout: { write: () => true }, stderr: { write: () => true }, env: {} });
}

// Release scripts branch on the flag: `if node src/cli.ts eval flags/storefront.json gift-cards; then ...`
test("eval exits 1 when the flag is off, so shell scripts can branch on it", () => {
  assert.equal(status(["eval", CONFIG, "gift-cards"]), 1);
  assert.equal(status(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "FR"]), 1);
  assert.equal(status(["eval", CONFIG, "dark-mode"]), 0);
  assert.equal(status(["eval", CONFIG, "new-checkout", "--user", "qa-anna"]), 0);
});
