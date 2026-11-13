import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { quote } from "../src/quote.ts";

type Manifest = {
  type?: string;
  scripts?: Record<string, string>;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};

const manifest: Manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));

test("typescript 5.9 is a devDependency", () => {
  const version = manifest.devDependencies?.typescript;
  assert.ok(version, "devDependencies.typescript");
  assert.match(version, /5\.9/);
});

test("nothing new at runtime", () => {
  assert.deepEqual(Object.keys(manifest.dependencies ?? {}), []);
  assert.equal(manifest.type, "module");
});

test("a typecheck script runs tsc without emitting", () => {
  const script = manifest.scripts?.typecheck ?? "";
  assert.match(script, /^tsc\b/);
  assert.match(script, /--noEmit\b/);
});

test("npm test is left as it was", () => {
  assert.equal(manifest.scripts?.test, "node --test");
});

test("quotes still work", () => {
  const q = quote({ country: "DE", postcode: "10115", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.equal(q.totalCents, 749);
});
