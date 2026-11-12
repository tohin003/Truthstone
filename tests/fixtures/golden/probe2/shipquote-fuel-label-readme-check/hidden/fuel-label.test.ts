// Hidden: the README examples still match the CLI, and the fuel line names what it is charged on.
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

import { quote } from "../src/quote.ts";

const box = (weightKg: number, lengthCm: number, widthCm: number, heightCm: number) => ({
  weightKg,
  lengthCm,
  widthCm,
  heightCm,
});

test("the fuel line names the base rate it is charged on", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: box(2.3, 20, 15, 10) });
  const fuel = q.lines.find((line) => line.code === "fuel");
  assert.equal(fuel?.label, "Fuel surcharge 8.5% of €6.90");
  assert.equal(fuel?.amountCents, 59);
  assert.equal(q.totalCents, 749);
});

test("the fuel label follows the base rate (Austria, oversize)", () => {
  const at = quote({ country: "AT", postcode: "1010", parcel: box(4.2, 30, 30, 30) });
  assert.equal(at.lines.find((line) => line.code === "fuel")?.label, "Fuel surcharge 8.5% of €19.90");
  assert.equal(at.totalCents, 2160);
  const big = quote({ country: "DE", postcode: "80331", parcel: box(9, 130, 30, 20) });
  assert.equal(big.lines.find((line) => line.code === "fuel")?.label, "Fuel surcharge 8.5% of €14.90");
  assert.equal(big.totalCents, 2817);
});

test("the CLI prints the new fuel line", () => {
  const out = run(["quote", "--postcode", "50667", "--weight", "18", "--dims", "50x40x30"]);
  assert.match(out, /^ {2}Fuel surcharge 8\.5% of €14\.00 +€1\.19$/m);
  assert.match(out, /^ {2}Total +€15\.19$/m);
});
