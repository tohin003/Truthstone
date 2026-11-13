// Output snapshots: the exact command-line output the checkout's support scripts read (npm run test:snapshots).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { main } from "../src/cli.ts";

type Case = { name: string; args: string[] };

const cases: Case[] = JSON.parse(readFileSync(new URL("./cases.json", import.meta.url), "utf8"));

function run(args: string[]): { status: number; stdout: string } {
  let stdout = "";
  const status = main(args, { stdout: { write: (text: string) => (stdout += text) }, stderr: { write: () => true } });
  return { status, stdout };
}

for (const { name, args } of cases) {
  test(`snapshot: ${name}`, () => {
    const expected = readFileSync(new URL(`./expected/${name}.txt`, import.meta.url), "utf8");
    const { status, stdout } = run(args);
    assert.equal(status, 0);
    assert.equal(stdout, expected);
  });
}
