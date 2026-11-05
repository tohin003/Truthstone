// QA smoke checks: expected decisions for known contexts, run against a config before a deploy.
//
//   node src/smoke.ts flags/storefront.json qa/storefront-smoke.jsonl
//
// Each line of the smoke file is {"flag": ..., "context": {...}, "expect": "<reason>"}.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadConfig } from "./config.ts";
import { evaluate } from "./evaluate.ts";
import type { Context } from "./types.ts";

export type SmokeCase = { flag: string; context: Context; expect: string };
export type SmokeResult = { passed: number; failures: string[] };

export function readSmoke(path: string): SmokeCase[] {
  return readFileSync(path, "utf8").split("\n").filter((line) => line.trim() !== "").map((line) => JSON.parse(line) as SmokeCase);
}

/** Evaluates every case (overrides off) and lists the ones whose reason is not the expected one. */
export function runSmoke(configPath: string, smokePath: string): SmokeResult {
  const config = loadConfig(configPath);
  const failures: string[] = [];
  let passed = 0;
  for (const { flag, context, expect } of readSmoke(smokePath)) {
    const { reason } = evaluate(config, flag, context, { env: {} });
    if (reason === expect) {
      passed += 1;
    } else {
      failures.push(`${flag} ${JSON.stringify(context)}: expected ${expect}, got ${reason}`);
    }
  }
  return { passed, failures };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [configPath, smokePath] = process.argv.slice(2);
  const { passed, failures } = runSmoke(configPath, smokePath);
  for (const failure of failures) {
    console.error(failure);
  }
  console.log(`${passed} passed, ${failures.length} failed`);
  process.exitCode = failures.length === 0 ? 0 : 1;
}
