import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { renderRateTable } from "../scripts/rate-table.ts";

const SCRIPT = fileURLToPath(new URL("../scripts/rate-table.ts", import.meta.url));

test("one row per weight bracket, one column per zone", () => {
  const lines = renderRateTable(2026).trimEnd().split("\n");
  assert.equal(lines[0], "| Weight | Germany North & East | Germany West & Centre | Germany South | Austria |");
  assert.equal(lines[1], "|---|---:|---:|---:|---:|");
  assert.equal(lines[2], "| up to 1 kg | €4.90 | €5.40 | €5.90 | €11.90 |");
  assert.equal(lines[7], "| up to 31.5 kg | €16.90 | €17.90 | €18.90 | €34.90 |");
  assert.equal(lines.length, 8);
});

test("the script prints the table for the year it is given", () => {
  const out = execFileSync(process.execPath, [SCRIPT, "--year", "2026"], { encoding: "utf8" });
  assert.equal(out, renderRateTable(2026));
});

test("flags the deploy pipeline adds are ignored", () => {
  const out = execFileSync(process.execPath, [SCRIPT, "--year", "2026", "--stage", "prod", "--build-id", "481"], {
    encoding: "utf8",
  });
  assert.equal(out, renderRateTable(2026));
});

test("a year without a rate card exits 1, a malformed year 2", () => {
  const missing = spawnSync(process.execPath, [SCRIPT, "--year", "2019"], { encoding: "utf8" });
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /no rate card for 2019/);
  assert.equal(spawnSync(process.execPath, [SCRIPT, "--year", "26"], { encoding: "utf8" }).status, 2);
});
