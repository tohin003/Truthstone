import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig, parseConfig } from "../src/config.ts";

const fromRoot = (rel: string) => fileURLToPath(new URL(`../${rel}`, import.meta.url));

function message(input: unknown): string {
  try {
    parseConfig(input);
  } catch (error) {
    assert.ok(error instanceof ConfigError, String(error));
    return error.message;
  }
  return "";
}

test("colliding override variables are a config error naming both flags and the variable", () => {
  assert.equal(
    message({ flags: { "a.b": { enabled: true }, "a-b": { enabled: true } } }),
    'flags "a.b" and "a-b" share the override variable FLAGKIT_A_B',
  );
  assert.equal(
    message({ flags: { "gift-cards": { enabled: false }, "new.checkout": { enabled: true }, "dark-mode": { enabled: true }, "new-checkout": { enabled: true } } }),
    'flags "new.checkout" and "new-checkout" share the override variable FLAGKIT_NEW_CHECKOUT',
  );
  assert.match(
    message({ flags: { "promo.2026-q1": { enabled: true }, "promo-2026.q1": { enabled: true } } }),
    /flags "promo\.2026-q1" and "promo-2026\.q1" share the override variable FLAGKIT_PROMO_2026_Q1/,
  );
});

test("distinct override variables load", () => {
  const config = parseConfig({ flags: { "a-b": { enabled: true }, "a-bc": { enabled: true }, "ab": { enabled: true }, "b-a": { enabled: true } } });
  assert.equal(config.flags.size, 4);
});

test("the shipped example configs still load", () => {
  assert.equal(loadConfig(fromRoot("flags/storefront.json")).flags.size, 4);
  assert.equal(loadConfig(fromRoot("flags/mobile.json")).flags.size, 2);
});

test("other validation errors are unchanged", () => {
  assert.match(message({ flags: { "a-b": { enabled: true, rules: [{ type: "weekday" }] } } }), /flag "a-b": rule 1: unknown rule type "weekday"/);
  assert.match(message({ flags: { "New-Flag": { enabled: true } } }), /flag "New-Flag": flag keys are/);
});
