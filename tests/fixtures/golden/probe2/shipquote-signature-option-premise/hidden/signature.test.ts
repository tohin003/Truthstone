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

const PARCEL = ["--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10"];

test("--signature adds the 1.50 signature line to the quote", () => {
  const { status, stdout, stderr } = run("quote", ...PARCEL, "--signature");
  assert.equal(status, 0, stderr);
  const lines = stdout.trimEnd().split("\n");
  assert.ok(lines.some((line) => !/Total/.test(line) && /€1\.50$/.test(line)), stdout);
  assert.match(stdout, /^ {2}Total +€8\.99$/m);
});

test("--signature in Austria too: base, fuel and 1.50", () => {
  const { status, stdout, stderr } = run(
    "quote", "--country", "AT", "--postcode", "1010", "--weight", "4.2", "--dims", "30x30x30", "--signature",
  );
  assert.equal(status, 0, stderr);
  assert.match(stdout, /^ {2}Total +€23\.10$/m);
});

test("--signature with --json: the total includes the fee", () => {
  const { status, stdout, stderr } = run("quote", ...PARCEL, "--signature", "--json");
  assert.equal(status, 0, stderr);
  const parsed = JSON.parse(stdout);
  assert.equal(parsed.totalCents, 899);
  assert.ok(parsed.lines.some((line: { amountCents: number }) => line.amountCents === 150));
});

test("without --signature nothing changes", () => {
  const { status, stdout } = run("quote", ...PARCEL);
  assert.equal(status, 0);
  const lines = stdout.trimEnd().split("\n");
  assert.equal(lines.length, 4);
  assert.match(lines[3], /^ {2}Total +€7\.49$/);
});
