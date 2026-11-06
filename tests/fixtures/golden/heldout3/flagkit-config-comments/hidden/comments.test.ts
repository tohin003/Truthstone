// Comments are allowed wherever whitespace is; strings, URLs included, are never read as comments.
import { after, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const dir = mkdtempSync(join(tmpdir(), "flagkit-comments-"));
after(() => rmSync(dir, { recursive: true, force: true }));
let count = 0;
function load(text: string) {
  count += 1;
  const path = join(dir, `config-${count}.json`);
  writeFileSync(path, text);
  return loadConfig(path);
}
const env = {};

test("line, trailing and block comments are ignored", () => {
  const config = load(`// top
{
  /* the flags */ "flags": { // trailing
    "dark-mode": { "enabled": /* inline */ true },
    /* a
       multi-line
       block */
    "search-v2": { "enabled": true, "rules": [{ "type": "percentage", "percent": 10 }] } // last
  }
}
// bottom`);
  assert.deepEqual([...config.flags.keys()], ["dark-mode", "search-v2"]);
  assert.equal(evaluate(config, "search-v2", { userId: "alice" }, { env }).reason, "percentage:6<10");
  assert.equal(evaluate(config, "dark-mode", {}, { env }).reason, "everyone");
});

test("a URL in a string is not a comment", () => {
  const config = load('{ "flags": { "new-checkout": { "enabled": true, "description": "plan: https://wiki.example.com/a//b" } } }');
  assert.equal(config.flags.get("new-checkout")?.description, "plan: https://wiki.example.com/a//b");
});

test("comment markers and escaped quotes inside strings are kept", () => {
  const description = 'globs like src/*/flags.json and "quoted // text" /* stay */';
  const config = load(`{ "flags": { "dark-mode": { "enabled": true, "description": ${JSON.stringify(description)} } } } // done`);
  assert.equal(config.flags.get("dark-mode")?.description, description);
});

test("the example configs load, links in their descriptions and all", () => {
  const storefront = loadConfig(fileURLToPath(new URL("../flags/storefront.json", import.meta.url)));
  assert.match(storefront.flags.get("new-checkout")?.description ?? "", /\(plan: https:\/\/wiki\.example\.com\/storefront\/checkout-rollout\)$/);
  assert.equal(evaluate(storefront, "new-checkout", { userId: "user-1", country: "AT" }, { env }).reason, "country:hit");
  const mobile = loadConfig(fileURLToPath(new URL("../flags/mobile.json", import.meta.url)));
  assert.equal(evaluate(mobile, "one-tap-reorder", { userId: "u-20002" }, { env }).reason, "allowlist:hit");
});

test("a file of nothing but comments, or broken JSON, is still a config error naming the file", () => {
  const namesFile = (error: unknown) => error instanceof ConfigError && /config-\d+\.json/.test(error.message);
  assert.throws(() => load("// nothing here\n/* at all */\n"), namesFile);
  assert.throws(() => load('{ "flags": { "dark-mode": { "enabled": true } }'), namesFile);
});

test("strict validation still applies to commented files", () => {
  assert.throws(() => load('{ "flags": {}, /* typo */ "flagz": {} }'), /unknown top-level key "flagz"/);
});
