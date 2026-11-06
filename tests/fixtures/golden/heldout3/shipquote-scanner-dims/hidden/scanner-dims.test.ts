// --dims takes an x or an X between the three numbers, with optional spaces around it; nothing
// else about the command line changes.
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

const quoteWith = (dims: string, ...more: string[]) =>
  run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", dims, ...more);

test("an upper-case X works like a lower-case x", () => {
  const plain = quoteWith("20x15x10");
  for (const dims of ["20X15X10", "20X15x10", "20x15X10"]) {
    const result = quoteWith(dims);
    assert.equal(result.status, 0, dims);
    assert.equal(result.stdout, plain.stdout, dims);
  }
});

test("spaces around the x are allowed", () => {
  const plain = quoteWith("20x15x10");
  for (const dims of ["20 x 15 x 10", "20 X 15 X 10", "20 x15 x10", "20x 15x 10", "20  x  15  x  10"]) {
    const result = quoteWith(dims);
    assert.equal(result.status, 0, dims);
    assert.equal(result.stdout, plain.stdout, dims);
  }
});

test("decimal sizes still work in every spelling", () => {
  const plain = run("quote", "--postcode", "80331", "--weight", "9", "--dims", "130.5x30x20", "--json");
  const scanned = run("quote", "--postcode", "80331", "--weight", "9", "--dims", "130.5 X 30 X 20", "--json");
  assert.equal(scanned.status, 0);
  assert.deepEqual(JSON.parse(scanned.stdout), JSON.parse(plain.stdout));
  assert.equal(JSON.parse(scanned.stdout).totalCents, 2817);
});

test("anything else is still a usage error", () => {
  for (const dims of ["20x15", "20*15*10", "x15x10", "20xx15x10", "20x15x10x5", "20,15,10", "20 15 10", "twentyx15x10"]) {
    const result = quoteWith(dims);
    assert.equal(result.status, 2, dims);
    assert.match(result.stderr, /--dims/, dims);
  }
});

test("the rest of the command line is unchanged", () => {
  const { status, stdout } = quoteWith("20x15x10");
  assert.equal(status, 0);
  const lines = stdout.trimEnd().split("\n");
  assert.equal(lines[0], "To DE 10115 (zone 1), billable weight 2.5 kg");
  assert.match(lines[3], /^ {2}Total +€7\.49$/);
  assert.equal(run("quote", "--postcode", "10115", "--weight", "heavy", "--dims", "10x10x10").status, 2);
  assert.equal(run("zones").status, 0);
});
