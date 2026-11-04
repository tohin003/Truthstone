import { test } from "node:test";
import assert from "node:assert/strict";
import { checkoutLabel, LANGS } from "../src/labels.ts";

test("the checkout is offered in English and German", () => {
  assert.deepEqual(LANGS, ["en", "de"]);
});

test("quote lines have English checkout labels", () => {
  assert.equal(checkoutLabel("base", "en"), "Shipping");
  assert.equal(checkoutLabel("fuel", "en"), "Fuel surcharge");
  assert.equal(checkoutLabel("remote"), "Remote area surcharge");
});

test("German labels come from the German catalogue", () => {
  assert.equal(checkoutLabel("base", "de"), "Versand");
  assert.equal(checkoutLabel("fuel", "de"), "Treibstoffzuschlag");
  assert.equal(checkoutLabel("remote", "de"), "Inselzuschlag");
});

test("a label not translated yet falls back to English", () => {
  assert.equal(checkoutLabel("total", "de"), "Total");
});

test("the translation platform's metadata is not a label", () => {
  assert.equal(checkoutLabel("_meta", "de"), "_meta");
});
