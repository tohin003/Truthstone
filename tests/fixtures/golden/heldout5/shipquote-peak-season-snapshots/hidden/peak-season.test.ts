import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { quote } from "../src/quote.ts";

const small = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const lines = (q: ReturnType<typeof quote>) => q.lines.map((line) => [line.code, line.amountCents]);
const at = (shipDate: string | undefined) =>
  quote({ country: "DE", postcode: "10115", parcel: small, ...(shipDate === undefined ? {} : { shipDate }) });

test("ship dates from 15 November to 31 December carry a last 90-cent peak line", () => {
  for (const date of ["2026-11-15", "2026-11-30", "2026-12-24", "2026-12-31", "2027-11-20", "2025-12-01"]) {
    const q = at(date);
    assert.deepEqual(lines(q), [["base", 690], ["fuel", 59], ["peak", 90]], date);
    assert.equal(q.lines.at(-1)?.label, "Peak season surcharge", date);
    assert.equal(q.totalCents, 839, date);
  }
});

test("outside peak season, or without a ship date, nothing changes", () => {
  for (const date of ["2026-11-14", "2027-01-01", "2026-06-30", "2026-01-02", undefined]) {
    const q = at(date);
    assert.deepEqual(lines(q), [["base", 690], ["fuel", 59]], String(date));
    assert.equal(q.totalCents, 749, String(date));
  }
});

test("the peak line comes after every other surcharge and fuel stays on the base rate", () => {
  const q = quote({
    country: "DE",
    postcode: "25980",
    parcel: { weightKg: 9, lengthCm: 130, widthCm: 30, heightCm: 20 },
    shipDate: "2026-12-14",
  });
  assert.deepEqual(lines(q), [["base", 1290], ["fuel", 110], ["remote", 450], ["oversize", 1200], ["peak", 90]]);
  assert.equal(q.totalCents, 3140);
  assert.equal(q.deliveryDate, "2026-12-15");
});

test("the command line shows the peak line", () => {
  let out = "";
  const status = main(["quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10", "--ship-date", "2026-12-01"], {
    stdout: { write: (text: string) => (out += text) },
    stderr: { write: () => true },
  });
  assert.equal(status, 0);
  assert.match(out, /Peak season surcharge\s+€0\.90\n/);
  assert.match(out, /Total\s+€8\.39\n/);
});
