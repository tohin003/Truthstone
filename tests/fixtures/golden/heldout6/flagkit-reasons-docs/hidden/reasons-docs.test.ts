import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const readme = readFileSync(fileURLToPath(new URL("../README.md", import.meta.url)), "utf8");

function reasonsSection(): string {
  const lines = readme.split("\n");
  const start = lines.findIndex((line) => /^#{2,4}\s.*\breasons?\b/i.test(line));
  assert.notEqual(start, -1, "no README heading about reasons");
  const level = (lines[start].match(/^#+/) ?? ["##"])[0].length;
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => {
    const heading = line.match(/^(#+)\s/);
    return heading !== null && heading[1].length <= level;
  });
  return (end === -1 ? rest : rest.slice(0, end)).join("\n");
}

test("the README has a reasons section listing every reason evaluate can give", () => {
  const section = reasonsSection();
  for (const reason of [
    "unknown-flag",
    "override:on",
    "override:off",
    "disabled",
    "everyone",
    "no-match",
    "country:hit",
    "country:miss",
    "plan:hit",
    "plan:miss",
    "allowlist:hit",
    "allowlist:miss",
    "percentage:no-user",
  ]) {
    assert.ok(section.includes(reason), reason);
  }
  assert.match(section, /percentage:\S*</);
  assert.match(section, /percentage:\S*>=/);
});

test("the rest of the README is still there", () => {
  for (const heading of ["## Config", "## Rules", "## Evaluation", "## Percentage rollouts", "## Environment overrides", "## Command line", "## Development"]) {
    assert.ok(readme.includes(heading), heading);
  }
  assert.ok(readme.includes("bucket = fnv1a32"));
});
