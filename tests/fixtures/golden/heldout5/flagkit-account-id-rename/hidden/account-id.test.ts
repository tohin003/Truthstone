import { test } from "node:test";
import assert from "node:assert/strict";
import { main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { contextFromHeaders } from "../src/context.ts";
import { evaluate } from "../src/evaluate.ts";
import { fileURLToPath } from "node:url";

const fromRoot = (rel: string) => fileURLToPath(new URL(`../${rel}`, import.meta.url));
const env = {};
const config = parseConfig({
  flags: {
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "percentage", percent: 20 },
      ],
    },
  },
});

test("allowlist and percentage rules read accountId", () => {
  assert.equal(evaluate(config, "new-checkout", { accountId: "qa-anna" } as never, { env }).reason, "allowlist:hit");
  // bucket("new-checkout", "user-3") is 1; bucket("new-checkout", "user-1") is 63
  assert.equal(evaluate(config, "new-checkout", { accountId: "user-3" } as never, { env }).reason, "percentage:1<20");
  assert.deepEqual(
    evaluate(config, "new-checkout", { accountId: "user-1" } as never, { env }).trace.map((step) => step.reason),
    ["allowlist:miss", "percentage:63>=20"],
  );
  assert.deepEqual(evaluate(config, "new-checkout", {}, { env }).trace.map((step) => step.reason), [
    "allowlist:miss",
    "percentage:no-user",
  ]);
});

test("userId is gone: a context that still says userId targets nobody", () => {
  const result = evaluate(config, "new-checkout", { userId: "qa-anna" } as never, { env });
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "no-match");
});

test("the X-User-Id header fills accountId", () => {
  assert.deepEqual(contextFromHeaders({ "X-User-Id": "qa-anna", "X-Country": "DE" }), { accountId: "qa-anna", country: "DE" });
  assert.equal(evaluate(config, "new-checkout", contextFromHeaders({ "x-user-id": "qa-anna" }), { env }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "new-checkout", contextFromHeaders({ "x-user-id": ["user-3"] }), { env }).reason, "percentage:1<20");
});

test("the CLI's --user option fills accountId", () => {
  let stdout = "";
  const status = main(["eval", fromRoot("flags/storefront.json"), "new-checkout", "--user", "qa-anna"], {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.equal(stdout, "on (allowlist:hit)\n");
});
