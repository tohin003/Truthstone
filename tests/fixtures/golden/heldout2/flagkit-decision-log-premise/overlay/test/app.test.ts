import { test } from "node:test";
import assert from "node:assert/strict";
import { isOn } from "../app/flags.ts";

test("the storefront wrapper reads the storefront config", () => {
  assert.equal(isOn("new-checkout", { userId: "qa-anna" }), true);
  assert.equal(isOn("gift-cards", { userId: "qa-anna" }), false);
  assert.equal(isOn("no-such-flag"), false);
});
