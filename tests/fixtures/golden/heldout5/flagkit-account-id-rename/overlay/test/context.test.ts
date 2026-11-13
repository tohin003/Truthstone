import { test } from "node:test";
import assert from "node:assert/strict";
import { contextFromHeaders } from "../src/context.ts";

test("country and plan come from their headers, in any header case", () => {
  assert.deepEqual(contextFromHeaders({ "X-Country": "DE", "x-plan": "plus" }), { country: "DE", plan: "plus" });
});

test("repeated headers use the first value; empty and unknown headers are ignored", () => {
  assert.deepEqual(contextFromHeaders({ "x-country": ["AT", "DE"], "x-plan": "  ", accept: "text/html" }), { country: "AT" });
  assert.deepEqual(contextFromHeaders({}), {});
});
