import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseConfig } from "../src/config.ts";
import { decisionEvent } from "../src/decisions.ts";
import { evaluate } from "../src/evaluate.ts";

const config = parseConfig({
  flags: {
    "one-tap-reorder": { enabled: true, rules: [{ type: "plan", values: ["plus", "business"] }] },
    "dark-mode": { enabled: true },
  },
});
const at = new Date("2026-11-02T09:30:00Z");
const env = {};

type Schema = {
  required: string[];
  additionalProperties: boolean;
  properties: Record<string, { type: string | string[]; pattern?: string; minLength?: number; format?: string }>;
};
const SCHEMA = JSON.parse(readFileSync(new URL("../schema/decision-event.schema.json", import.meta.url), "utf8")) as Schema;

/** The parts of JSON Schema the warehouse schema uses: required, additionalProperties, type, pattern, minLength, date-time. */
function problems(event: Record<string, unknown>): string[] {
  const found: string[] = [];
  for (const key of SCHEMA.required) {
    if (!(key in event)) found.push(`missing ${key}`);
  }
  for (const [key, value] of Object.entries(event)) {
    const rule = SCHEMA.properties[key];
    if (!rule) {
      if (!SCHEMA.additionalProperties) found.push(`unexpected ${key}`);
      continue;
    }
    const types = Array.isArray(rule.type) ? rule.type : [rule.type];
    const actual = value === null ? "null" : typeof value;
    if (!types.includes(actual)) found.push(`${key} is ${actual}`);
    if (typeof value === "string" && rule.pattern && !new RegExp(rule.pattern).test(value)) found.push(`${key} pattern`);
    if (typeof value === "string" && rule.minLength && value.length < rule.minLength) found.push(`${key} too short`);
    if (typeof value === "string" && rule.format === "date-time" && Number.isNaN(Date.parse(value))) found.push(`${key} not a date-time`);
  }
  return found;
}

test("a decision event records the flag, the outcome, the reason, the user and the time", () => {
  const result = evaluate(config, "one-tap-reorder", { userId: "u-20001", plan: "plus" }, { env });
  const event = decisionEvent(result, { userId: "u-20001", plan: "plus" }, at);
  assert.equal(event.flag, "one-tap-reorder");
  assert.equal(event.enabled, true);
  assert.equal(event.reason, "plan:hit");
  assert.equal(event.userId, "u-20001");
  assert.equal(event.at, "2026-11-02T09:30:00.000Z");
});

test("anonymous evaluations have a null userId", () => {
  const result = evaluate(config, "dark-mode", {}, { env });
  assert.equal(decisionEvent(result, {}, at).userId, null);
});

test("decision events validate against the warehouse schema", () => {
  const contexts = [{ userId: "u-20001", plan: "plus" }, { userId: "u-3", plan: "free" }, {}];
  for (const context of contexts) {
    for (const flag of ["one-tap-reorder", "dark-mode", "missing-flag"]) {
      const event = decisionEvent(evaluate(config, flag, context, { env }), context, at);
      assert.deepEqual(problems(event as unknown as Record<string, unknown>), [], `${flag} ${JSON.stringify(context)}`);
    }
  }
});

test("decision events carry the user's plan for segmentation", () => {
  // Growth segments every rollout by plan: the event has to say which plan the user was on.
  const context = { userId: "u-20002", plan: "business" };
  const event = decisionEvent(evaluate(config, "one-tap-reorder", context, { env }), context, at) as unknown as Record<string, unknown>;
  assert.equal(event.plan, "business");
});
