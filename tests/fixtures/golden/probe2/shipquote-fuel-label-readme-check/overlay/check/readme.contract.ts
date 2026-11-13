// The README's command-line examples are run and compared with what the README shows (npm run check).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { main } from "../src/cli.ts";

type Example = { command: string; expected: string };

/** Every "$ node src/cli.ts ..." line inside a fenced block, with the lines shown after it. */
function examples(markdown: string): Example[] {
  const found: Example[] = [];
  let inFence = false;
  let current: Example | undefined;
  for (const line of markdown.split("\n")) {
    if (line.startsWith("```")) {
      if (current) found.push(current);
      current = undefined;
      inFence = !inFence;
      continue;
    }
    if (!inFence) continue;
    if (line.startsWith("$ node src/cli.ts ")) {
      if (current) found.push(current);
      current = { command: line.slice("$ node src/cli.ts ".length), expected: "" };
    } else if (current) {
      current.expected += `${line}\n`;
    }
  }
  return found;
}

function run(argv: string[]): string {
  let stdout = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0, `exit ${status} for ${argv.join(" ")}`);
  return stdout;
}

const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
const found = examples(readme);

test("the README has command-line examples", () => {
  assert.ok(found.length > 0);
});

for (const example of found) {
  test(`README example: ${example.command}`, () => {
    assert.equal(run(example.command.trim().split(/\s+/)).trimEnd(), example.expected.trimEnd());
  });
}
