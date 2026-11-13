import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { envOverride } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

// Added with #63 (override expiry); see "Environment overrides" in the README.
const before = new Date("2026-11-20T17:59:59Z");
const at = new Date("2026-11-20T18:00:00Z");

test("an override with an expiry holds until that instant, then is ignored", () => {
  const env = { FLAGKIT_DARK_MODE: "off until 2026-11-20T18:00Z" };
  assert.equal(envOverride("dark-mode", env, before), false);
  assert.equal(envOverride("dark-mode", env, at), undefined);
});

test("offsets, seconds and any case are honoured", () => {
  const env = { FLAGKIT_DARK_MODE: " ON Until 2026-11-20T23:30:00+05:30 " };
  assert.equal(envOverride("dark-mode", env, before), true);
  assert.equal(envOverride("dark-mode", env, at), undefined);
});

test("a date alone lasts to the end of that day in UTC", () => {
  const env = { FLAGKIT_DARK_MODE: "off until 2026-11-20" };
  assert.equal(envOverride("dark-mode", env, new Date("2026-11-20T23:59:59Z")), false);
  assert.equal(envOverride("dark-mode", env, new Date("2026-11-21T00:00:00Z")), undefined);
});

test("an expiry without a zone, or that is not a time, makes the value invalid", () => {
  for (const value of ["off until 2026-11-20T18:00", "off until tomorrow", "off until", "off until 2026-11-20T18:00Z later"]) {
    assert.equal(envOverride("dark-mode", { FLAGKIT_DARK_MODE: value }, before), undefined, value);
  }
});

test("evaluate reads the current time from options.now", () => {
  const config = parseConfig({ flags: { "dark-mode": { enabled: true } } });
  const env = { FLAGKIT_DARK_MODE: "off until 2026-11-20T18:00Z" };
  assert.equal(evaluate(config, "dark-mode", {}, { env, now: before }).reason, "override:off");
  assert.equal(evaluate(config, "dark-mode", {}, { env, now: at }).reason, "everyone");
});
