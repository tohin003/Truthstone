// transitBusinessDays replaces transitDays everywhere: quotes, the JSON output, the notices, the docs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { main } from "../src/cli.ts";
import { renderNotice } from "../src/notices.ts";
import { quote } from "../src/quote.ts";

const parcel = { weightKg: 1, lengthCm: 20, widthCm: 15, heightCm: 10 };
const fields = (q: unknown) => q as Record<string, unknown>;

function cli(...argv: string[]) {
  let stdout = "";
  const status = main(argv, { stdout: { write: (text: string) => (stdout += text) }, stderr: { write: () => true } });
  return { status, stdout };
}

test("a quote with a ship date carries transitBusinessDays and no transitDays", () => {
  const austria = fields(quote({ country: "AT", postcode: "1010", parcel, shipDate: "2026-11-05" }));
  assert.equal(austria.transitBusinessDays, 3);
  assert.equal(austria.deliveryDate, "2026-11-10");
  assert.equal(austria.transitDays, undefined);
  assert.equal(fields(quote({ country: "DE", postcode: "80331", parcel, shipDate: "2026-11-05" })).transitBusinessDays, 2);
});

test("a quote without a ship date carries neither", () => {
  const q = fields(quote({ country: "DE", postcode: "10115", parcel }));
  assert.equal(q.transitBusinessDays, undefined);
  assert.equal(q.transitDays, undefined);
  assert.equal(q.deliveryDate, undefined);
});

test("quote --json shows transitBusinessDays and no transitDays", () => {
  const argv = ["quote", "--country", "AT", "--postcode", "1010", "--weight", "1", "--dims", "20x15x10", "--ship-date", "2026-11-05", "--json"];
  const { status, stdout } = cli(...argv);
  assert.equal(status, 0);
  const parsed = JSON.parse(stdout);
  assert.equal(parsed.transitBusinessDays, 3);
  assert.equal(parsed.transitDays, undefined);
});

test("the printed quote still ends with the delivery estimate", () => {
  const at = cli("quote", "--country", "AT", "--postcode", "1010", "--weight", "1", "--dims", "20x15x10", "--ship-date", "2026-11-05");
  assert.match(at.stdout, /^Delivery: 2026-11-10 \(3 business days\)$/m);
  const de = cli("quote", "--postcode", "10115", "--weight", "1", "--dims", "20x15x10", "--ship-date", "2026-11-05");
  assert.match(de.stdout, /^Delivery: 2026-11-06 \(1 business day\)$/m);
});

test("the delivery-estimate notice still names the business days", () => {
  const q = quote({ country: "AT", postcode: "1010", parcel, shipDate: "2026-11-05" });
  assert.equal(renderNotice("delivery-estimate", q), "Your parcel to 1010 should arrive on 2026-11-10, 3 business days after pickup.\n");
});

test("the quote summary is unchanged", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.equal(renderNotice("quote-summary", q), "Shipping to DE 10115 (Germany North & East): €7.49, billed at 2.5 kg.\n");
});

test("the README documents transitBusinessDays", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  assert.match(readme, /transitBusinessDays/);
  assert.doesNotMatch(readme, /transitDays/);
});
