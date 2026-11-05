import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadConfig } from "../src/config.ts";

const dir = mkdtempSync(join(tmpdir(), "flagkit-positions-"));

function file(name: string, text: string): string {
  const path = join(dir, name);
  writeFileSync(path, text);
  return path;
}

function messageOf(path: string): string {
  try {
    loadConfig(path);
  } catch (error) {
    return (error as Error).message;
  }
  return "no error";
}

/**
 * Config errors name the position of the problem (FLAG-58), so people can jump to it:
 *
 *   <file>:<line>:<column>: <message>      e.g. flags/x.json:7:9: flag "x": rule 2: unknown rule type "weekday"
 *
 * Lines and columns are 1-based; columns count characters (a tab is one); \n, \r\n and \r end a line.
 * - An error about a rule points at the rule: its first character (the `{` of an object).
 * - An error about a flag points at the flag's key (its opening quote) inside "flags".
 * - An unknown top-level key points at that key.
 * - Errors about the document as a whole keep the plain form: `<file>: <message>`.
 * Invalid JSON and unreadable files are reported as before.
 */

test("a rule error points at the rule", () => {
  assert.equal(messageOf(file("v-rule.json", "{\n  \"flags\": {\n    \"new-checkout\": {\n      \"enabled\": true,\n      \"rules\": [\n        { \"type\": \"country\", \"values\": [\"DE\"] },\n        { \"type\": \"weekday\", \"values\": [\"sat\"] }\n      ]\n    }\n  }\n}\n")), `${join(dir, "v-rule.json")}:7:9: flag "new-checkout": rule 2: unknown rule type "weekday"`);
  assert.equal(messageOf(file("v-percent.json", "{\n  \"flags\": {\n    \"search-v2\": {\n      \"enabled\": true,\n      \"rules\": [{ \"type\": \"percentage\", \"percent\": 120 }]\n    }\n  }\n}\n")), `${join(dir, "v-percent.json")}:5:17: flag "search-v2": rule 1: "percent" must be a whole number from 0 to 100`);
});

test("a flag error points at the flag's key", () => {
  assert.equal(messageOf(file("v-field.json", "{\n  \"flags\": {\n    \"search-v2\": { \"enabled\": true },\n    \"dark-mode\": { \"enabled\": true, \"colour\": \"black\" }\n  }\n}\n")), `${join(dir, "v-field.json")}:4:5: flag "dark-mode": unknown field "colour"`);
  assert.equal(messageOf(file("v-mini.json", "{\"flags\":{\"a\":{\"enabled\":true},\"b\":{\"enabled\":\"yes\"}}}")), `${join(dir, "v-mini.json")}:1:32: flag "b": "enabled" must be true or false`);
});

test("an unknown top-level key points at the key", () => {
  assert.equal(messageOf(file("v-top.json", "{\n  \"flags\": {},\n  \"owner\": \"web-team\"\n}\n")), `${join(dir, "v-top.json")}:3:3: unknown top-level key "owner"`);
});

test("whole-document errors keep the plain form", () => {
  assert.equal(messageOf(file("v-doc.json", "[]\n")), `${join(dir, "v-doc.json")}: a config must be a JSON object`);
});
