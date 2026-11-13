import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { rateCard, RateError } from "../src/rates.ts";

function run(...argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: (text: string) => (stderr += text) },
  });
  return { status, stdout, stderr };
}

const PARCEL = ["--weight", "1", "--dims", "20x15x10"];

test("a one-day delivery reads 1 business day", () => {
  const { status, stdout } = run("quote", "--postcode", "10115", ...PARCEL, "--ship-date", "2026-11-05");
  assert.equal(status, 0);
  assert.match(stdout, /^Delivery: 2026-11-06 \(1 business day\)$/m);
});

test("longer deliveries still read business days", () => {
  const south = run("quote", "--postcode", "80331", ...PARCEL, "--ship-date", "2026-11-05");
  assert.match(south.stdout, /^Delivery: 2026-11-09 \(2 business days\)$/m);
  const austria = run("quote", "--country", "AT", "--postcode", "1010", ...PARCEL, "--ship-date", "2026-11-05");
  assert.match(austria.stdout, /^Delivery: 2026-11-10 \(3 business days\)$/m);
});

test("the quote lines are unchanged and no estimate without a ship date", () => {
  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");
  assert.equal(status, 0);
  assert.equal(stdout.trimEnd().split("\n").length, 4);
  assert.match(stdout, /^ {2}Total +€7\.49$/m);
  assert.doesNotMatch(stdout, /Delivery/);
});

test("there is still no 2027 rate card (no placeholder prices)", () => {
  assert.throws(() => rateCard(2027), RateError);
  assert.equal(run("quote", "--postcode", "10115", ...PARCEL, "--year", "2027").status, 1);
});
