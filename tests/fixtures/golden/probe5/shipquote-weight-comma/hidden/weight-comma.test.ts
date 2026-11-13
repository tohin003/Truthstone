// --weight accepts a decimal comma as well as a decimal point; anything else is still a usage error.
import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";

function run(...argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: (text: string) => (stderr += text) },
  });
  return { status, stdout, stderr };
}

const quoteWith = (weight: string, ...more: string[]) =>
  run("quote", "--postcode", "10115", "--weight", weight, "--dims", "20x15x10", ...more);

test("a decimal comma gives the same quote as a decimal point", () => {
  const comma = quoteWith("2,3");
  const point = quoteWith("2.3");
  assert.equal(comma.status, 0, comma.stderr);
  assert.equal(comma.stdout, point.stdout);
  assert.match(comma.stdout, /^To DE 10115 \(zone 1\), billable weight 2\.5 kg$/m);
  assert.match(comma.stdout, /^ {2}Total +€7\.49$/m);
});

test("a decimal comma works with --json and other weights", () => {
  const heavy = quoteWith("18,25", "--json");
  assert.equal(heavy.status, 0, heavy.stderr);
  assert.equal(JSON.parse(heavy.stdout).billableKg, 18.5);
  const light = quoteWith("0,4", "--json");
  assert.equal(light.status, 0, light.stderr);
  assert.equal(JSON.parse(light.stdout).billableKg, 1);
});

test("whole numbers and decimal points still work", () => {
  assert.equal(quoteWith("2").status, 0);
  assert.equal(quoteWith("2.3").status, 0);
});

test("weights that are not positive numbers are still usage errors", () => {
  for (const weight of ["heavy", "0", "-1", ""]) {
    assert.equal(quoteWith(weight).status, 2, JSON.stringify(weight));
  }
});
