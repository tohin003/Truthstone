import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { readSmoke, runSmoke } from "../src/smoke.ts";

const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

function smokeFile(lines: object[]): string {
  const path = join(mkdtempSync(join(tmpdir(), "smoke-")), "smoke.jsonl");
  writeFileSync(path, lines.map((line) => JSON.stringify(line)).join("\n") + "\n");
  return path;
}

test("readSmoke reads one case per line and skips blank lines", () => {
  const path = smokeFile([{ flag: "dark-mode", context: {}, expect: "everyone" }]);
  assert.deepEqual(readSmoke(path), [{ flag: "dark-mode", context: {}, expect: "everyone" }]);
});

test("runSmoke reports the cases whose reason differs", () => {
  const path = smokeFile([
    { flag: "dark-mode", context: {}, expect: "everyone" },
    { flag: "gift-cards", context: {}, expect: "everyone" },
  ]);
  const result = runSmoke(storefront, path);
  assert.equal(result.passed, 1);
  assert.deepEqual(result.failures, ['gift-cards {}: expected everyone, got disabled']);
});
