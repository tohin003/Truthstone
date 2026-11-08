// The data team's schema, as published (a copy kept with these tests): every decision event must validate.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseConfig } from "../src/config.ts";
import { decisionEvent } from "../src/decisions.ts";
import { evaluate } from "../src/evaluate.ts";

type Rule = { type: string | string[]; pattern?: string; minLength?: number; format?: string };
const SCHEMA = JSON.parse(readFileSync(new URL("./decision-event.schema.json", import.meta.url), "utf8")) as {
  required: string[];
  properties: Record<string, Rule>;
};
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

function violations(event: object): string[] {
  const found: string[] = [];
  const record = event as Record<string, unknown>;
  for (const key of SCHEMA.required) {
    if (!Object.hasOwn(record, key)) found.push(`missing ${key}`);
  }
  for (const key of Object.getOwnPropertyNames(record)) {
    const rule = SCHEMA.properties[key];
    if (!rule) {
      found.push(`unexpected ${key}`);
      continue;
    }
    const value = record[key];
    const types = Array.isArray(rule.type) ? rule.type : [rule.type];
    if (!types.includes(value === null ? "null" : typeof value)) found.push(`${key} has the wrong type`);
    if (typeof value === "string" && rule.pattern && !new RegExp(rule.pattern).test(value)) found.push(`${key} pattern`);
    if (typeof value === "string" && rule.minLength && value.length < rule.minLength) found.push(`${key} too short`);
    if (typeof value === "string" && rule.format === "date-time" && !ISO_UTC.test(value)) found.push(`${key} not a date-time`);
  }
  return found;
}

const config = parseConfig({
  flags: {
    "one-tap-reorder": { enabled: true, rules: [{ type: "plan", values: ["plus", "business"] }] },
    "offline-cart": { enabled: false },
    "dark-mode": { enabled: true },
  },
});
const at = new Date("2026-11-03T18:05:09Z");
const env = {};
const CONTEXTS = [
  { userId: "u-20002", plan: "business" },
  { userId: "u-20001", plan: "plus" },
  { userId: "u-7", plan: "free" },
  { plan: "plus" },
  {},
];

test("every decision event validates against the data team's schema, plans or not", () => {
  for (const context of CONTEXTS) {
    for (const flag of ["one-tap-reorder", "offline-cart", "dark-mode", "nope"]) {
      const event = decisionEvent(evaluate(config, flag, context, { env }), context, at);
      assert.deepEqual(violations(event), [], `${flag} ${JSON.stringify(context)}`);
      assert.deepEqual(violations(JSON.parse(JSON.stringify(event))), [], `${flag} ${JSON.stringify(context)} as sent`);
    }
  }
});

test("no context attribute besides userId reaches an event", () => {
  const context = { userId: "u-20002", plan: "business" };
  const event = decisionEvent(evaluate(config, "one-tap-reorder", context, { env }), context, at);
  assert.equal("plan" in event, false);
  assert.equal(JSON.stringify(event).includes("business"), false);
});

test("events still record the evaluation as documented", () => {
  const context = { userId: "u-20001", plan: "plus" };
  assert.deepEqual(decisionEvent(evaluate(config, "one-tap-reorder", context, { env }), context, at), {
    flag: "one-tap-reorder",
    enabled: true,
    reason: "plan:hit",
    userId: "u-20001",
    at: "2026-11-03T18:05:09.000Z",
  });
  const anonymous = decisionEvent(evaluate(config, "offline-cart", {}, { env }), {}, at);
  assert.deepEqual([anonymous.enabled, anonymous.reason, anonymous.userId], [false, "disabled", null]);
});

test("evaluation itself is unchanged", () => {
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "business" }, { env }).reason, "plan:hit");
  assert.equal(evaluate(config, "one-tap-reorder", { plan: "free" }, { env }).reason, "no-match");
});
