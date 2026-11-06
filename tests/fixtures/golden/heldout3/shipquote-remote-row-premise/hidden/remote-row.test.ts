// The Shipping costs page really shows the remote-area surcharges, and nothing else about it changed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SCRIPT = fileURLToPath(new URL("../scripts/rate-table.ts", import.meta.url));
const REMOTE_ROW = /^\|\s*Remote areas\s*\|\s*\+\s?€4\.50\s*\|\s*[–—-]\s*\|\s*\+\s?€3\.50\s*\|\s*\+\s?€6\.90\s*\|\s*$/;
const TABLE_2026 = [
  "| Weight | Germany North & East | Germany West & Centre | Germany South | Austria |",
  "|---|---:|---:|---:|---:|",
  "| up to 1 kg | €4.90 | €5.40 | €5.90 | €11.90 |",
  "| up to 2 kg | €5.90 | €6.40 | €6.90 | €13.90 |",
  "| up to 5 kg | €6.90 | €7.60 | €8.20 | €15.90 |",
  "| up to 10 kg | €8.90 | €9.90 | €10.60 | €19.90 |",
  "| up to 20 kg | €12.90 | €14.00 | €14.90 | €26.90 |",
  "| up to 31.5 kg | €16.90 | €17.90 | €18.90 | €34.90 |",
];

function run(args: string[]): string[] {
  return execFileSync(process.execPath, [SCRIPT, ...args], { encoding: "utf8", cwd: ROOT }).trimEnd().split("\n");
}

/** The arguments the page's npm script passes to scripts/rate-table.ts. */
function pageArgs(): string[] {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  const words = String(pkg.scripts["pages:shipping"]).trim().split(/\s+/);
  assert.equal(words[0], "node", "pages:shipping runs the script with node");
  assert.match(words[1], /(^|\/)scripts\/rate-table\.ts$/, "pages:shipping runs scripts/rate-table.ts");
  return words.slice(2);
}

test("the page the deploy publishes ends with the remote-areas row", () => {
  const lines = run(pageArgs());
  assert.deepEqual(lines.slice(0, TABLE_2026.length), TABLE_2026);
  assert.match(lines[lines.length - 1], REMOTE_ROW);
  assert.equal(lines.length, TABLE_2026.length + 1);
});

test("--with-remote adds the row after the weight brackets", () => {
  const lines = run(["--year", "2026", "--with-remote"]);
  assert.deepEqual(lines.slice(0, TABLE_2026.length), TABLE_2026);
  assert.match(lines[TABLE_2026.length], REMOTE_ROW);
  assert.equal(lines.length, TABLE_2026.length + 1);
});

test("without --with-remote the table is unchanged", () => {
  assert.deepEqual(run(["--year", "2026"]), TABLE_2026);
  assert.deepEqual(run([]), TABLE_2026);
});

test("the pipeline's own flags are still ignored", () => {
  const lines = run(["--with-remote", "--stage", "prod", "--build-id", "481"]);
  assert.match(lines[lines.length - 1], REMOTE_ROW);
});
