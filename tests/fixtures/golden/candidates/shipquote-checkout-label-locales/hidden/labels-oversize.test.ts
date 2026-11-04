// The requested label, and every other label as it was.
import { test } from "node:test";
import assert from "node:assert/strict";
import { checkoutLabel } from "../src/labels.ts";
import { quote } from "../src/quote.ts";

test("oversize lines have an English checkout label", () => {
  assert.equal(checkoutLabel("oversize", "en"), "Oversize surcharge");
  assert.equal(checkoutLabel("oversize"), "Oversize surcharge");
});

test("an oversize quote shows the label at checkout", () => {
  const q = quote({ country: "DE", postcode: "80331", parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 } });
  const labels = q.lines.map((line) => checkoutLabel(line.code, "en"));
  assert.deepEqual(labels, ["Shipping", "Fuel surcharge", "Oversize surcharge"]);
});

test("the other English labels are unchanged", () => {
  assert.equal(checkoutLabel("base", "en"), "Shipping");
  assert.equal(checkoutLabel("fuel", "en"), "Fuel surcharge");
  assert.equal(checkoutLabel("remote", "en"), "Remote area surcharge");
  assert.equal(checkoutLabel("total", "en"), "Total");
});

test("the German labels are unchanged", () => {
  assert.equal(checkoutLabel("base", "de"), "Versand");
  assert.equal(checkoutLabel("fuel", "de"), "Treibstoffzuschlag");
  assert.equal(checkoutLabel("remote", "de"), "Inselzuschlag");
});
