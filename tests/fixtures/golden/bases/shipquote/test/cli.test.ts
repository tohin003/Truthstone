import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
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

test("quote prints the lines, the total and the zone", () => {
  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");
  assert.equal(status, 0);
  const lines = stdout.trimEnd().split("\n");
  assert.equal(lines[0], "To DE 10115 (zone 1), billable weight 2.5 kg");
  assert.match(lines[1], /^ {2}Base rate, zone 1 \(Germany North & East\), up to 5 kg +€6\.90$/);
  assert.match(lines[2], /^ {2}Fuel surcharge 8\.5% +€0\.59$/);
  assert.match(lines[3], /^ {2}Total +€7\.49$/);
  assert.equal(lines.length, 4);
});

test("quote with a ship date adds the delivery estimate", () => {
  const { status, stdout } = run(
    "quote", "--country", "AT", "--postcode", "1010", "--weight", "1", "--dims", "20x15x10", "--ship-date", "2026-11-05",
  );
  assert.equal(status, 0);
  assert.match(stdout, /^To AT 1010 \(zone 4\), billable weight 1\.0 kg$/m);
  assert.match(stdout, /^Delivery: 2026-11-10 \(3 business days\)$/m);
});

test("quote --json prints the quote object", () => {
  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--json");
  assert.equal(status, 0);
  const parsed = JSON.parse(stdout);
  assert.equal(parsed.totalCents, 749);
  assert.equal(parsed.zone, 1);
});

test("zones lists every zone with what it covers", () => {
  const { status, stdout } = run("zones");
  assert.equal(status, 0);
  const lines = stdout.trimEnd().split("\n");
  assert.equal(lines.length, 4);
  assert.match(lines[0], /^zone 1 {2}Germany North & East +DE 0xxxx-2xxxx$/);
  assert.match(lines[3], /^zone 4 {2}Austria +AT \(all postcodes\)$/);
});

test("usage errors exit 2 and print the usage", () => {
  const missing = run("quote", "--weight", "1", "--dims", "10x10x10");
  assert.equal(missing.status, 2);
  assert.match(missing.stderr, /--postcode is required/);
  assert.match(missing.stderr, /usage: shipquote/);
  assert.equal(run("ship").status, 2);
  assert.equal(run("quote", "--postcode", "10115", "--weight", "heavy", "--dims", "10x10x10").status, 2);
});

test("bad destinations exit 1 with the reason", () => {
  const { status, stderr } = run("quote", "--postcode", "1011", "--weight", "1", "--dims", "10x10x10");
  assert.equal(status, 1);
  assert.equal(stderr, 'shipquote: not a German postcode: "1011"\n');
});

test("--help prints the usage", () => {
  const { status, stdout } = run("--help");
  assert.equal(status, 0);
  assert.match(stdout, /^usage: shipquote <command>/);
});

test("the script runs from the command line", () => {
  const script = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
  const out = execFileSync(process.execPath, [script, "zones"], { encoding: "utf8" });
  assert.match(out, /^zone 1 /);
});
