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

test("the visible expectations", () => {
  assert.equal(messageOf(file("v-rule.json", "{\n  \"flags\": {\n    \"new-checkout\": {\n      \"enabled\": true,\n      \"rules\": [\n        { \"type\": \"country\", \"values\": [\"DE\"] },\n        { \"type\": \"weekday\", \"values\": [\"sat\"] }\n      ]\n    }\n  }\n}\n")), `${join(dir, "v-rule.json")}:7:9: flag "new-checkout": rule 2: unknown rule type "weekday"`);
  assert.equal(messageOf(file("v-percent.json", "{\n  \"flags\": {\n    \"search-v2\": {\n      \"enabled\": true,\n      \"rules\": [{ \"type\": \"percentage\", \"percent\": 120 }]\n    }\n  }\n}\n")), `${join(dir, "v-percent.json")}:5:17: flag "search-v2": rule 1: "percent" must be a whole number from 0 to 100`);
  assert.equal(messageOf(file("v-field.json", "{\n  \"flags\": {\n    \"search-v2\": { \"enabled\": true },\n    \"dark-mode\": { \"enabled\": true, \"colour\": \"black\" }\n  }\n}\n")), `${join(dir, "v-field.json")}:4:5: flag "dark-mode": unknown field "colour"`);
  assert.equal(messageOf(file("v-mini.json", "{\"flags\":{\"a\":{\"enabled\":true},\"b\":{\"enabled\":\"yes\"}}}")), `${join(dir, "v-mini.json")}:1:32: flag "b": "enabled" must be true or false`);
  assert.equal(messageOf(file("v-top.json", "{\n  \"flags\": {},\n  \"owner\": \"web-team\"\n}\n")), `${join(dir, "v-top.json")}:3:3: unknown top-level key "owner"`);
  assert.equal(messageOf(file("v-doc.json", "[]\n")), `${join(dir, "v-doc.json")}: a config must be a JSON object`);
});

test("tabs, CRLF line ends, strings with braces and quotes, nested values", () => {
  assert.equal(messageOf(file("h-tabs.json", "{\n\t\"flags\": {\n\t\t\"a\": {\n\t\t\t\"enabled\": true,\n\t\t\t\"rules\": [\n\t\t\t\t{\"type\": \"plan\", \"values\": []}\n\t\t\t]\n\t\t}\n\t}\n}\n")), `${join(dir, "h-tabs.json")}:6:5: flag "a": rule 1: "values" must be a non-empty list of plan names`);
  assert.equal(messageOf(file("h-crlf.json", "{\n  \"flags\": {\n    \"a\": { \"enabled\": true },\n    \"b\": { \"enabled\": 1 }\n  }\n}\n")), `${join(dir, "h-crlf.json")}:4:5: flag "b": "enabled" must be true or false`);
  assert.equal(messageOf(file("h-strings.json", "{\n  \"flags\": {\n    \"a\": { \"enabled\": true, \"description\": \"uses \\\"quotes\\\", {braces} and [brackets]: caf\u00e9\", \"rules\": [{ \"type\": \"country\", \"values\": [\"DE\"] }, { \"type\": \"country\", \"values\": [\"de\"] }] }\n  }\n}\n")), `${join(dir, "h-strings.json")}:3:145: flag "a": rule 2: "values" must be a non-empty list of two-letter upper-case country codes`);
  assert.equal(messageOf(file("h-nested.json", "{\n  \"flags\": {\n    \"a\": { \"enabled\": true, \"rules\": [ { \"type\": \"allowlist\", \"values\": [\"x\", \"y\"] } ] },\n    \"b\": { \"enabled\": true, \"rules\": [ { \"type\": \"allowlist\", \"values\": [\"x\"] }, { \"type\": \"plan\", \"values\": [\"p\"], \"extra\": [1, [2, {\"k\": 3}]] } ] }\n  }\n}\n")), `${join(dir, "h-nested.json")}:4:82: flag "b": rule 2: unknown field "extra"`);
});

test("values that are not objects and keys that are not valid", () => {
  assert.equal(messageOf(file("h-notobject.json", "{\n  \"flags\": {\n    \"a\": {\n      \"enabled\": true,\n      \"rules\": [\n        42\n      ]\n    },\n    \"b\": 5\n  }\n}\n")), `${join(dir, "h-notobject.json")}:6:9: flag "a": rule 1: must be an object`);
  assert.equal(messageOf(file("h-flagnotobject.json", "{\n  \"flags\": {\n    \"ok\": { \"enabled\": false },\n      \"b\": 5\n  }\n}\n")), `${join(dir, "h-flagnotobject.json")}:4:7: flag "b": must be an object`);
  assert.equal(messageOf(file("h-badkey.json", "{\n  \"flags\": {\n    \"Bad_Key\": { \"enabled\": true }\n  }\n}\n")), `${join(dir, "h-badkey.json")}:3:5: flag "Bad_Key": flag keys are lower-case letters and digits, separated by single dots or hyphens`);
  assert.equal(messageOf(file("h-flags-not-object.json", "{ \"flags\": [] }\n")), `${join(dir, "h-flags-not-object.json")}: "flags" must be an object of flag definitions`);
});

test("invalid JSON is reported as before", () => {
  assert.match(messageOf(file("broken.json", '{ "flags": { "a": ')), /broken\.json is not valid JSON/);
});
