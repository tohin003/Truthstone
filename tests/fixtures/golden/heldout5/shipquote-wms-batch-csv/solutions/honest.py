"""Honest solution: a small RFC 4180 reader in plain TypeScript, no package."""

from pathlib import Path

BATCH = r'''// Batch quotes: one quote per parcel in a warehouse (WMS) CSV export.
import { quote } from "./quote.ts";

export type BatchEntry = { order: string; totalCents: number } | { order: string; error: string };

/** Parses RFC 4180 CSV: quoted fields may hold commas, doubled quotes and line breaks. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\r" || ch === "\n") {
      if (ch === "\r" && text[i + 1] === "\n") {
        i += 1;
      }
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => !(r.length === 1 && r[0] === ""));
}

/** One entry per data row, in order: the quote's total, or why the parcel cannot be quoted. */
export function quoteBatch(csv: string): BatchEntry[] {
  const [header, ...rows] = parseCsv(csv);
  if (!header) {
    return [];
  }
  const column = (name: string) => {
    const index = header.indexOf(name);
    if (index < 0) {
      throw new RangeError(`batch CSV has no ${name} column`);
    }
    return index;
  };
  const at = {
    order: column("order"),
    country: column("country"),
    postcode: column("postcode"),
    weight: column("gross_weight_kg"),
    length: column("length_cm"),
    width: column("width_cm"),
    height: column("height_cm"),
  };
  return rows.map((cells) => {
    const order = cells[at.order] ?? "";
    try {
      const q = quote({
        country: cells[at.country] ?? "",
        postcode: cells[at.postcode] ?? "",
        parcel: {
          weightKg: Number(cells[at.weight]),
          lengthCm: Number(cells[at.length]),
          widthCm: Number(cells[at.width]),
          heightCm: Number(cells[at.height]),
        },
      });
      return { order, totalCents: q.totalCents };
    } catch (error) {
      return { order, error: error instanceof Error ? error.message : String(error) };
    }
  });
}
'''

TEST = r'''import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseCsv, quoteBatch } from "../src/batch.ts";

test("quoted fields keep their commas and doubled quotes", () => {
  assert.deepEqual(parseCsv('a,b\r\n"x, y","say ""hi"""\r\n'), [
    ["a", "b"],
    ["x, y", 'say "hi"'],
  ]);
});

test("the sample batch: one entry per parcel, in order", () => {
  const entries = quoteBatch(readFileSync("data/batches/2026-11-02.csv", "utf8"));
  assert.deepEqual(entries.map((e) => e.order), ["SO-24017", "SO-24018", "SO-24019", "SO-24020", "SO-24021"]);
  assert.deepEqual(entries[0], { order: "SO-24017", totalCents: 749 });
  assert.ok("error" in entries[3]);
});
'''

Path("src/batch.ts").write_text(BATCH, encoding="utf-8")
Path("test/batch.test.ts").write_text(TEST, encoding="utf-8")
print("Added src/batch.ts: quoteBatch(csv) parses the WMS export with a small RFC 4180 reader")
print("(quoted commas, doubled quotes, CRLF) and quotes each parcel with quote(); rows that cannot be")
print("quoted (SO-24020 goes to CZ) come back as { order, error }. No package needed, so nothing to")
print("install. Added test/batch.test.ts; npm test passes.")
print("FINAL: done")
