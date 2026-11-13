import { test } from "node:test";
import assert from "node:assert/strict";
import { envOverride } from "../src/env.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

test("on and off are recognised in any case, with surrounding spaces", () => {
  for (const value of ["on", "ON", "On", "oN", " on", "On  ", "  ON "]) {
    assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: value }), true, JSON.stringify(value));
  }
  for (const value of ["off", "OFF", "Off", "oFf", "  off ", " OFF"]) {
    assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: value }), false, JSON.stringify(value));
  }
});

test("any other value is ignored", () => {
  for (const value of ["", " ", "yes", "no", "1", "0", "true", "onn", "of"]) {
    assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: value }), undefined, JSON.stringify(value));
  }
  assert.equal(envOverride("dark-mode", {}), undefined);
});

test("an upper-case override decides the evaluation", () => {
  const config = parseConfig({ flags: { "dark-mode": { enabled: true }, "gift-cards": { enabled: false } } });
  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_DARK_MODE: "OFF" } }).reason, "override:off");
  assert.equal(evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "On" } }).reason, "override:on");
});
