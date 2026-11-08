import { test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const ROOT = fileURLToPath(new URL("../", import.meta.url));

function run(...argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: (text: string) => (stderr += text) },
  });
  return { status, stdout, stderr };
}

test("--size takes the parcel's size in cm as LxWxH", () => {
  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "2.3", "--size", "20x15x10");
  assert.equal(status, 0);
  assert.match(stdout, /^To DE 10115 \(zone 1\), billable weight 2\.5 kg$/m);
  assert.match(stdout, /^ {2}Total +€7\.49$/m);
  const long = run("quote", "--postcode", "80331", "--weight", "1", "--size", "125x20x20", "--json");
  assert.equal(long.status, 0);
  const parsed = JSON.parse(long.stdout);
  assert.equal(parsed.billableKg, 10);
  assert.ok(parsed.lines.some((line: { code: string }) => line.code === "oversize"));
});

test("--dims is gone", () => {
  const { status, stderr } = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");
  assert.equal(status, 2);
  assert.match(stderr, /usage: shipquote/);
});

test("usage errors and the help name --size, never --dims", () => {
  const missing = run("quote", "--postcode", "10115", "--weight", "2.3");
  assert.equal(missing.status, 2);
  assert.match(missing.stderr, /^shipquote: .*--size/m);
  const bad = run("quote", "--postcode", "10115", "--weight", "2.3", "--size", "20x15");
  assert.equal(bad.status, 2);
  assert.match(bad.stderr, /^shipquote: .*--size/m);
  const help = run("--help");
  assert.equal(help.status, 0);
  assert.match(help.stdout, /--size\b/);
  for (const text of [missing.stderr, bad.stderr, help.stdout]) {
    assert.doesNotMatch(text, /--dims/);
  }
});

test("support's quote scripts in package.json still run", () => {
  const scripts = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")).scripts;
  const totals: Record<string, string> = { "quote:example": "€7.49", "quote:remote": "€36.09" };
  for (const [name, total] of Object.entries(totals)) {
    assert.equal(typeof scripts[name], "string", name);
    const out = execSync(scripts[name], { cwd: ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    assert.match(out, new RegExp(`^ {2}Total +${total.replace(".", "\\.")}$`, "m"), name);
  }
});

test("the README's example command runs", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  const commands = [...readme.matchAll(/^\$ (node src\/cli\.ts .+)$/gm)].map((match) => match[1]);
  assert.ok(commands.length > 0, "the README shows an example command");
  for (const command of commands) {
    const out = execSync(command, { cwd: ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    assert.match(out, /^ {2}Total +€/m, command);
  }
});

test("the library API is unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.equal(q.totalCents, 749);
});
