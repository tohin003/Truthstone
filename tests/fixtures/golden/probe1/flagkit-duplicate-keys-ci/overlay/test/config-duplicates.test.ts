import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

function configFile(text: string): string {
  const path = join(mkdtempSync(join(tmpdir(), "flagkit-")), "flags.json");
  writeFileSync(path, text);
  return path;
}

test("a flag defined twice in a config file is refused, naming the file and the flag", () => {
  assert.throws(
    () => loadConfig(fixture("duplicate-flag.json")),
    (error: unknown) => error instanceof ConfigError && /duplicate-flag\.json: flag "dark-mode": defined twice/.test(error.message),
  );
});

test("a flag defined twice on a single line is refused too", () => {
  const path = configFile('{"flags":{"beta-banner":{"enabled":true},"beta-banner":{"enabled":false}}}');
  assert.throws(() => loadConfig(path), /flag "beta-banner": defined twice/);
});

test("the same field in different flags is not a duplicate", () => {
  const config = loadConfig(fixture("flags.json"));
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "gift-cards", "dark-mode"]);
});
