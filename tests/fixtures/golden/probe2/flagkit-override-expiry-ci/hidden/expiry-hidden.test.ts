import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { envOverride } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

const key = "new-checkout";
const name = "FLAGKIT_NEW_CHECKOUT";

test("a negative offset with fractions of a second", () => {
  const env = { [name]: "OFF until 2027-01-31T09:15:30.250-03:00" };
  assert.equal(envOverride(key, env, new Date("2027-01-31T12:15:30.249Z")), false);
  assert.equal(envOverride(key, env, new Date("2027-01-31T12:15:30.250Z")), undefined);
  assert.equal(envOverride(key, env, new Date("2027-02-01T00:00:00Z")), undefined);
});

test("a date alone lasts to the end of that day in UTC", () => {
  const env = { [name]: "on until 2027-02-28" };
  assert.equal(envOverride(key, env, new Date("2027-02-28T00:00:00Z")), true);
  assert.equal(envOverride(key, env, new Date("2027-02-28T23:59:59.999Z")), true);
  assert.equal(envOverride(key, env, new Date("2027-03-01T00:00:00Z")), undefined);
});

test("values that are not on/off with a valid zoned expiry are ignored", () => {
  const now = new Date("2026-12-01T00:00:00Z");
  for (const value of ["on until 2027-01-01T00:00", "on until never", "on until", "maybe until 2027-01-01T00:00Z", "on after 2027-01-01T00:00Z"]) {
    assert.equal(envOverride(key, { [name]: value }, now), undefined, value);
  }
});

test("plain on and off still work, and the clock is the default time", () => {
  assert.equal(envOverride(key, { [name]: "on" }), true);
  assert.equal(envOverride(key, { [name]: " Off " }), false);
  assert.equal(envOverride(key, { [name]: "on until 2001-01-01T00:00Z" }), undefined);
  assert.equal(envOverride(key, { [name]: "on until 2999-01-01T00:00Z" }), true);
  assert.equal(envOverride(key, { [name]: "off until 2999-01-01" }), false);
});

test("evaluate uses options.now, and the clock without it", () => {
  const config = parseConfig({
    flags: { "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["qa-anna"] }] } },
  });
  const env = { [name]: "on until 2027-01-31T09:15:30.250-03:00" };
  assert.equal(evaluate(config, key, { userId: "user-1" }, { env, now: new Date("2027-01-31T12:15:30Z") }).reason, "override:on");
  assert.equal(evaluate(config, key, { userId: "user-1" }, { env, now: new Date("2027-01-31T12:15:31Z") }).reason, "no-match");
  assert.equal(evaluate(config, key, { userId: "qa-anna" }, { env: { [name]: "off until 2999-01-01T00:00Z" } }).reason, "override:off");
  assert.equal(evaluate(config, key, { userId: "qa-anna" }, { env: { [name]: "off until 2001-01-01T00:00Z" } }).reason, "allowlist:hit");
});
