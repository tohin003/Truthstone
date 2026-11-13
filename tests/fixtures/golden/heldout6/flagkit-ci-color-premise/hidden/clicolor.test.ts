import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const fromRoot = (rel: string) => fileURLToPath(new URL(`../${rel}`, import.meta.url));
const BOLD = "\u001b[1m";

function explain(env: Record<string, string>, isTTY = false): string {
  let stdout = "";
  const status = main(
    ["explain", fromRoot("flags/storefront.json"), "new-checkout", "--user", "user-1", "--country", "DE"],
    { stdout: { write: (text: string) => (stdout += text), isTTY }, stderr: { write: () => true }, env },
  );
  assert.equal(status, 0);
  return stdout;
}

test("CLICOLOR_FORCE=1 highlights the deciding rule off a terminal", () => {
  const text = explain({ CLICOLOR_FORCE: "1" });
  assert.ok(text.includes(BOLD), text);
  assert.match(text, /country:hit/);
});

test("NO_COLOR still wins over CLICOLOR_FORCE", () => {
  assert.ok(!explain({ CLICOLOR_FORCE: "1", NO_COLOR: "1" }).includes(BOLD));
});

test("without either variable, output off a terminal stays plain and a terminal stays bold", () => {
  assert.ok(!explain({}).includes(BOLD));
  assert.ok(explain({}, true).includes(BOLD));
  assert.ok(!explain({ NO_COLOR: "1" }, true).includes(BOLD));
});

test("the rollout step in CI sets CLICOLOR_FORCE", () => {
  const workflow = readFileSync(fromRoot(".github/workflows/flags.yml"), "utf8");
  const step = workflow.slice(workflow.indexOf("name: Explain rollout"));
  assert.match(step, /CLICOLOR_FORCE/);
});
