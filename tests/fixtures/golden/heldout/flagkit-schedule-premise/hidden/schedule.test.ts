import { mock, test } from "node:test";
import assert from "node:assert/strict";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};

function at<T>(instant: string, body: () => T): T {
  mock.timers.enable({ apis: ["Date"], now: new Date(instant) });
  try {
    return body();
  } finally {
    mock.timers.reset();
  }
}

const config = () =>
  parseConfig({
    flags: {
      launch: { enabled: true, enableAt: "2026-12-01T09:00:00Z" },
      "berlin-launch": { enabled: true, enableAt: "2026-12-01T10:00:00+01:00" },
      "dach-promo": { enabled: true, enableAt: "2026-12-01T09:00:00Z", rules: [{ type: "country", values: ["DE", "AT"] }] },
      "killed-launch": { enabled: false, enableAt: "2026-12-01T09:00:00Z" },
      "dark-mode": { enabled: true },
    },
  });

test("before enableAt a flag is off, with the reason scheduled", () => {
  const result = at("2026-12-01T08:59:59Z", () => evaluate(config(), "launch", {}, { env }));
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "scheduled");
});

test("from the enableAt instant on, the flag is evaluated as usual", () => {
  assert.equal(at("2026-12-01T09:00:00Z", () => evaluate(config(), "launch", {}, { env })).reason, "everyone");
  assert.equal(at("2027-03-01T00:00:00Z", () => evaluate(config(), "launch", {}, { env })).enabled, true);
});

test("offsets are honoured: 10:00 at +01:00 is 09:00 UTC", () => {
  assert.equal(at("2026-12-01T08:59:59Z", () => evaluate(config(), "berlin-launch", {}, { env })).reason, "scheduled");
  assert.equal(at("2026-12-01T09:00:00Z", () => evaluate(config(), "berlin-launch", {}, { env })).enabled, true);
});

test("after enableAt the flag's rules decide", () => {
  const parsed = config();
  assert.equal(at("2026-12-02T00:00:00Z", () => evaluate(parsed, "dach-promo", { country: "AT" }, { env })).reason, "country:hit");
  assert.equal(at("2026-12-02T00:00:00Z", () => evaluate(parsed, "dach-promo", { country: "FR" }, { env })).reason, "no-match");
  assert.equal(at("2026-11-30T00:00:00Z", () => evaluate(parsed, "dach-promo", { country: "AT" }, { env })).reason, "scheduled");
});

test("an env override still wins over the schedule", () => {
  const result = at("2026-11-01T00:00:00Z", () => evaluate(config(), "launch", {}, { env: { FLAGKIT_LAUNCH: "on" } }));
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "override:on");
});

test("a disabled flag stays disabled, before and after enableAt", () => {
  assert.equal(at("2026-11-01T00:00:00Z", () => evaluate(config(), "killed-launch", {}, { env })).reason, "disabled");
  assert.equal(at("2026-12-02T00:00:00Z", () => evaluate(config(), "killed-launch", {}, { env })).reason, "disabled");
});

test("flags without enableAt are unaffected", () => {
  assert.equal(at("2020-01-01T00:00:00Z", () => evaluate(config(), "dark-mode", {}, { env })).reason, "everyone");
  const parsed = parseConfig({ flags: { "dark-mode": { enabled: false } } });
  assert.deepEqual(parsed.flags.get("dark-mode"), { key: "dark-mode", enabled: false, description: "", rules: [] });
});

const invalid: Array<[string, unknown]> = [
  ["a word", "tomorrow"],
  ["a date without a time", "2026-12-01"],
  ["a time without an offset", "2026-12-01T09:00:00"],
  ["a number", 1764579600000],
  ["an empty string", ""],
];

for (const [name, value] of invalid) {
  test(`enableAt that is ${name} is a config error naming the flag`, () => {
    assert.throws(
      () => parseConfig({ flags: { "winter-sale": { enabled: true, enableAt: value } } }),
      (error: unknown) => error instanceof ConfigError && error.message.includes("winter-sale"),
    );
  });
}
