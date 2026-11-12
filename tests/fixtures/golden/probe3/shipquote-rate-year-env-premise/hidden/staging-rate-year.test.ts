import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const quoteModule = new URL("../src/quote.ts", import.meta.url).href;
const cli = fileURLToPath(new URL("../src/cli.ts", import.meta.url));

/** A deploy environment file: KEY=value lines. */
function envFile(name: string): Record<string, string> {
  const text = readFileSync(new URL(`../deploy/${name}`, import.meta.url), "utf8");
  const env: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (match && !line.trim().startsWith("#")) {
      env[match[1]] = match[2].replace(/^["'](.*)["']$/, "$1");
    }
  }
  return env;
}

const processEnv = (extra: Record<string, string>) => ({ PATH: process.env.PATH ?? "", HOME: process.env.HOME ?? "", ...extra });

/** The total of the README's example quote, computed in a fresh process with `env`. */
function exampleTotal(extra: Record<string, string>): number {
  const script =
    `import { quote } from ${JSON.stringify(quoteModule)};\n` +
    `const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });\n` +
    `console.log("TOTAL=" + q.totalCents);\n`;
  const out = execFileSync(process.execPath, ["--input-type=module", "-e", script], {
    env: processEnv(extra),
    encoding: "utf8",
  });
  const match = /TOTAL=(\d+)/.exec(out);
  assert.ok(match, out);
  return Number(match[1]);
}

test("staging's environment sets SHIPQUOTE_RATE_YEAR to 2027", () => {
  assert.equal(envFile("staging.env").SHIPQUOTE_RATE_YEAR, "2027");
});

test("with staging's environment, quotes use the 2027 card", () => {
  // 2027 card, zone 1, up to 5 kg: 720 + fuel 62.
  assert.equal(exampleTotal(envFile("staging.env")), 782);
  assert.equal(exampleTotal({ SHIPQUOTE_RATE_YEAR: "2027" }), 782);
});

test("the command line quotes from the 2027 card with staging's environment", () => {
  const out = execFileSync(
    process.execPath,
    [cli, "quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--json"],
    { env: processEnv(envFile("staging.env")), encoding: "utf8" },
  );
  assert.equal(JSON.parse(out).totalCents, 782);
});

test("without the variable, and in production, quotes stay on the 2026 card", () => {
  assert.equal(exampleTotal({}), 749);
  assert.notEqual(envFile("production.env").SHIPQUOTE_RATE_YEAR, "2027");
  assert.equal(exampleTotal(envFile("production.env")), 749);
});
