import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";

function configFile(text: string): string {
  const path = join(mkdtempSync(join(tmpdir(), "flagkit-hidden-")), "flags.json");
  writeFileSync(path, text);
  return path;
}

const refused = (text: string, flag: string) =>
  assert.throws(
    () => loadConfig(configFile(text)),
    (error: unknown) => error instanceof ConfigError && error.message.includes(`flag "${flag}": defined twice`),
  );

test("a repeated flag is refused, wherever the copies are and however the file is laid out", () => {
  refused(`{"flags": {"a-b": {"enabled": true}, "c-d": {"enabled": true}, "a-b": {"enabled": true}}}`, "a-b");
  refused(`{\n  "flags" : {\n    "search.v2" :{ "enabled": true },\n\t"search.v2":\n{"enabled":false,"rules":[]}\n  }\n}\n`, "search.v2");
  refused(`{"flags":{"x-y":{"enabled":true,"rules":[{"type":"plan","values":["pro"]}]},"x-y":{"enabled":true}}}`, "x-y");
});

test("the error names the file", () => {
  const path = configFile(`{"flags":{"a-b":{"enabled":true},"a-b":{"enabled":true}}}`);
  assert.throws(() => loadConfig(path), (error: unknown) => error instanceof ConfigError && error.message.startsWith(`${path}: `));
});

test("keys repeated in different flags or rules are fine", () => {
  const config = loadConfig(
    configFile(
      JSON.stringify({
        flags: {
          "new-checkout": { enabled: true, description: "one", rules: [{ type: "plan", values: ["pro"] }, { type: "plan", values: ["team"] }] },
          "dark-mode": { enabled: true, description: "two", rules: [{ type: "plan", values: ["pro"] }] },
        },
      }, null, 2),
    ),
  );
  assert.deepEqual([...config.flags.keys()], ["new-checkout", "dark-mode"]);
});

test("a flag key inside a string or a rule's values is not a second definition", () => {
  const text = `{"flags": {
    "old-banner": {"enabled": false, "description": "replaced by \\"new-banner\\": see the redesign"},
    "new-banner": {"enabled": true, "description": "\\"old-banner\\": {\\"enabled\\": true} was the old one",
                   "rules": [{"type": "allowlist", "values": ["old-banner", "new-banner"]}]}
  }}`;
  const config = loadConfig(configFile(text));
  assert.deepEqual([...config.flags.keys()], ["old-banner", "new-banner"]);
  assert.equal(config.flags.get("old-banner")?.description, 'replaced by "new-banner": see the redesign');
});

test("the example configs still load", () => {
  for (const name of ["storefront.json", "mobile.json"]) {
    const config = loadConfig(fileURLToPath(new URL(`../flags/${name}`, import.meta.url)));
    assert.ok(config.flags.size > 0, name);
  }
});

test("other config errors are unchanged", () => {
  assert.throws(() => loadConfig(configFile("{")), /is not valid JSON/);
  assert.throws(() => loadConfig(configFile(`{"flags": {"a-b": {"enabled": true, "owner": "me"}}}`)), /flag "a-b": unknown field "owner"/);
});
