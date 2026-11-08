import { test } from "node:test";
import assert from "node:assert/strict";
import { contextFromHeaders } from "../src/headers.ts";

test("the user id and plan come from their headers, trimmed", () => {
  assert.deepEqual(contextFromHeaders({ "x-user-id": " u-10234 ", "x-customer-plan": "plus" }), {
    userId: "u-10234",
    plan: "plus",
  });
});

test("missing and blank headers leave their field out", () => {
  assert.deepEqual(contextFromHeaders({}), {});
  assert.deepEqual(contextFromHeaders({ "x-user-id": "  ", "x-customer-plan": undefined }), {});
});

test("a repeated header counts by its first value", () => {
  assert.deepEqual(contextFromHeaders({ "x-user-id": ["u-1", "u-2"] }), { userId: "u-1" });
});

test("unrelated headers are ignored", () => {
  assert.deepEqual(contextFromHeaders({ "user-agent": "curl/8", "x-user-id": "u-7" }), { userId: "u-7" });
});
