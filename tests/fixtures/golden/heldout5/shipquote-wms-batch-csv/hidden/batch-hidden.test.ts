import { test } from "node:test";
import assert from "node:assert/strict";
import { quoteBatch } from "../src/batch.ts";
import { quote } from "../src/quote.ts";

const HEADER = "order,customer,country,postcode,gross_weight_kg,length_cm,width_cm,height_cm";
const csv = (...rows: string[]) => [HEADER, ...rows].join("\r\n") + "\r\n";
const total = (country: string, postcode: string, w: number, l: number, wi: number, h: number) =>
  quote({ country, postcode, parcel: { weightKg: w, lengthCm: l, widthCm: wi, heightCm: h } }).totalCents;

test("one entry per parcel, in order, with the quote's total", () => {
  const entries = quoteBatch(
    csv("SO-1,Becker,DE,10115,2.3,20,15,10", "SO-2,Hofmann GmbH,DE,50667,18,50,40,30", "SO-3,Wien Shop,AT,1010,0.8,30,20,5"),
  );
  assert.deepEqual(entries, [
    { order: "SO-1", totalCents: total("DE", "10115", 2.3, 20, 15, 10) },
    { order: "SO-2", totalCents: total("DE", "50667", 18, 50, 40, 30) },
    { order: "SO-3", totalCents: total("AT", "1010", 0.8, 30, 20, 5) },
  ]);
  assert.equal(entries[0] && "totalCents" in entries[0] && entries[0].totalCents, 749);
});

test("quoted fields may contain commas and doubled quotes", () => {
  const entries = quoteBatch(
    csv(
      'SO-4,"Becker, Jonas",DE,10115,2.3,20,15,10',
      'SO-5,"Café ""Zur Linde"", Inh. Graf",AT,1010,0.8,30,20,5',
      'SO-6,"Lindqvist, ""Söhne""","DE","80331","4.6","60","40","40"',
    ),
  );
  assert.deepEqual(entries, [
    { order: "SO-4", totalCents: total("DE", "10115", 2.3, 20, 15, 10) },
    { order: "SO-5", totalCents: total("AT", "1010", 0.8, 30, 20, 5) },
    { order: "SO-6", totalCents: total("DE", "80331", 4.6, 60, 40, 40) },
  ]);
});

test("a parcel that cannot be quoted gets an error and the rest are still quoted", () => {
  const entries = quoteBatch(
    csv("SO-7,Novak,CZ,11000,1.2,20,20,10", "SO-8,Becker,DE,10115,2.3,20,15,10", "SO-9,Heavy,DE,10115,40,20,20,20"),
  );
  assert.equal(entries.length, 3);
  const [cz, ok, heavy] = entries as Array<Record<string, unknown>>;
  assert.equal(cz.order, "SO-7");
  assert.equal(typeof cz.error, "string");
  assert.ok((cz.error as string).length > 0);
  assert.equal(cz.totalCents, undefined);
  assert.deepEqual(ok, { order: "SO-8", totalCents: total("DE", "10115", 2.3, 20, 15, 10) });
  assert.equal(heavy.order, "SO-9");
  assert.equal(typeof heavy.error, "string");
});

test("a header-only export has no entries", () => {
  assert.deepEqual(quoteBatch(HEADER + "\r\n"), []);
});
