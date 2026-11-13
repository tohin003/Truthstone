import { test } from "node:test";
import assert from "node:assert/strict";
import { envOverride } from "../src/env.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

test("on and off are honoured in any case, with surrounding whitespace", () => {
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: " On " }), true);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "\toff\n" }), false);
  assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: "ON" }), true);
  assert.equal(envOverride("search.v2", { FLAGKIT_SEARCH_V2: "off " }), false);
});

test("anything else is still ignored", () => {
  for (const value of ["", "   ", "yes", "o n", "onn", "1"]) {
    assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: value }), undefined, JSON.stringify(value));
  }
  assert.equal(envOverride("dark-mode", {}), undefined);
});

test("a spaced override wins in evaluation", () => {
  const config = parseConfig({ flags: { "gift-cards": { enabled: false } } });
  assert.equal(evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: " on" } }).reason, "override:on");
});
