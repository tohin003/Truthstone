// The documented override values: exactly "on" and "off" (any case, spaces ignored); anything else is ignored.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { envOverride } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

test("true, false, 1, 0 and other words do not override a flag", () => {
  for (const value of ["false", "true", "TRUE", "1", "0", " 0 ", "yes", "no", "enabled", "disable", ""]) {
    assert.equal(envOverride("search.v2", { FLAGKIT_SEARCH_V2: value }), undefined, JSON.stringify(value));
  }
});

test("on and off still override, in any case and with spaces", () => {
  assert.equal(envOverride("search.v2", { FLAGKIT_SEARCH_V2: "off" }), false);
  assert.equal(envOverride("search.v2", { FLAGKIT_SEARCH_V2: " ON " }), true);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "Off" }), false);
});

test("evaluation ignores a false or 0 override and applies the rules", () => {
  const config = parseConfig({ flags: { "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 10 }] } } });
  // bucket("search-v2", "alice") is 6
  for (const value of ["false", "0"]) {
    const result = evaluate(config, "search-v2", { userId: "alice" }, { env: { FLAGKIT_SEARCH_V2: value } });
    assert.equal(result.enabled, true, value);
    assert.equal(result.reason, "percentage:6<10", value);
  }
  const off = evaluate(config, "search-v2", { userId: "alice" }, { env: { FLAGKIT_SEARCH_V2: "off" } });
  assert.deepEqual([off.enabled, off.reason], [false, "override:off"]);
});

test("the command line ignores a true override too", () => {
  const config = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));
  let stdout = "";
  const status = main(["eval", config, "gift-cards"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
    env: { FLAGKIT_GIFT_CARDS: "true" },
  });
  assert.equal(status, 0);
  assert.equal(stdout, "off (disabled)\n");
});
