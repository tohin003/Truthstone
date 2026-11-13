import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { formatReport, rolloutReport, sampleUsers } from "../src/report.ts";

const config = parseConfig({
  flags: {
    "new-checkout": { enabled: true, rules: [{ type: "allowlist", values: ["user-1", "user-2"] }] },
    "gift-cards": { enabled: false },
    "dark-mode": { enabled: true },
  },
});

test("the report counts the users each flag is on for, in config order", () => {
  assert.deepEqual(rolloutReport(config, sampleUsers(4)), [
    { flag: "new-checkout", on: 2, total: 4 },
    { flag: "gift-cards", on: 0, total: 4 },
    { flag: "dark-mode", on: 4, total: 4 },
  ]);
});

test("the report as text", () => {
  assert.equal(
    formatReport(rolloutReport(config, sampleUsers(4))),
    "new-checkout  2/4  50%\ngift-cards    0/4  0%\ndark-mode     4/4  100%\n",
  );
});
