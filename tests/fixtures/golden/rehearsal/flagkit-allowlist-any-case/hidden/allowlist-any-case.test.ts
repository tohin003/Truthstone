import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.ts";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};
const FLAGS = {
  flags: {
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["QA-Anna", "u-10234"] },
        { type: "country", values: ["DE"] },
        { type: "percentage", percent: 20 },
      ],
    },
    "search-v2": { enabled: true, rules: [{ type: "percentage", percent: 10 }] },
    "offline-cart": { enabled: true, rules: [{ type: "percentage", percent: 50 }] },
  },
};
const config = parseConfig(FLAGS);
const reasons = (flag: string, userId: string, country = "FR") =>
  evaluate(config, flag, { userId, country }, { env }).trace.map((step) => step.reason);

test("allowlist entries match user ids in any case, written either way", () => {
  for (const id of ["QA-Anna", "qa-anna", "QA-ANNA", "qA-aNNa", " qa-anna ", "u-10234", "U-10234"]) {
    assert.equal(evaluate(config, "new-checkout", { userId: id, country: "FR" }, { env }).reason, "allowlist:hit", id);
  }
});

test("other ids still miss the allowlist", () => {
  for (const id of ["qa-ann", "qa-anna2", "u-1023", "QA Anna", ""]) {
    assert.equal(reasons("new-checkout", id)[0], "allowlist:miss", JSON.stringify(id));
  }
  assert.equal(evaluate(config, "new-checkout", { userId: "qa-ben", country: "DE" }, { env }).reason, "country:hit");
});

test("percentage buckets still use the id as given: mixed-case ids keep their buckets", () => {
  // bucket(new-checkout, User-1) = 19 and (user-1) = 63; (search-v2, Alice) = 94, (ALICE) = 34,
  // (alice) = 6; (offline-cart, U-77810) = 42 and (u-77810) = 98.
  assert.deepEqual(reasons("new-checkout", "User-1"), ["allowlist:miss", "country:miss", "percentage:19<20"]);
  assert.deepEqual(reasons("new-checkout", "user-1"), ["allowlist:miss", "country:miss", "percentage:63>=20"]);
  assert.deepEqual(reasons("search-v2", "Alice"), ["percentage:94>=10"]);
  assert.deepEqual(reasons("search-v2", "ALICE"), ["percentage:34>=10"]);
  assert.deepEqual(reasons("search-v2", "alice"), ["percentage:6<10"]);
  assert.deepEqual(reasons("offline-cart", "U-77810"), ["percentage:42<50"]);
  assert.deepEqual(reasons("offline-cart", " U-77810 "), ["percentage:42<50"]);
  assert.deepEqual(reasons("offline-cart", "u-77810"), ["percentage:98>=50"]);
});

test("the CLI agrees", () => {
  const dir = mkdtempSync(join(tmpdir(), "fk-case-"));
  const path = join(dir, "flags.json");
  writeFileSync(path, JSON.stringify(FLAGS));
  const run = (argv: string[]) => {
    let stdout = "";
    const status = main(argv, { stdout: { write: (text: string) => (stdout += text), isTTY: false }, stderr: { write: () => true }, env: {} });
    return { status, stdout };
  };
  assert.deepEqual(run(["eval", path, "new-checkout", "--user", "qa-anna"]), { status: 0, stdout: "on (allowlist:hit)\n" });
  assert.equal(run(["eval", path, "new-checkout", "--user", "User-1", "--country", "FR"]).stdout, "on (percentage:19<20)\n");
  assert.equal(run(["eval", path, "offline-cart", "--user", "u-77810"]).stdout, "off (no-match)\n");
});

test("country rules still match in any case", () => {
  assert.equal(evaluate(config, "new-checkout", { userId: "nobody", country: "de" }, { env }).reason, "country:hit");
});
