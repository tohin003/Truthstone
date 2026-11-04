import { test } from "node:test";
import assert from "node:assert/strict";
import * as flagkit from "../src/index.ts";

test("the public API exports parsing, evaluation and hashing", () => {
  for (const name of ["parseConfig", "loadConfig", "evaluate", "bucket", "fnv1a32", "envName", "envOverride", "matcherFor"]) {
    assert.equal(typeof (flagkit as Record<string, unknown>)[name], "function", name);
  }
});

test("a flag evaluated through the public API", () => {
  const config = flagkit.parseConfig({ flags: { "dark-mode": { enabled: true } } });
  assert.equal(flagkit.evaluate(config, "dark-mode", {}, { env: {} }).enabled, true);
});
