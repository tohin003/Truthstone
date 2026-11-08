import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";
import { main } from "../src/cli.ts";

const CONFIG = fileURLToPath(new URL("./expiry-flags.json", import.meta.url));
const env = {};

function flagWith(fields: Record<string, unknown>) {
  return parseConfig({ flags: { "promo-banner": { enabled: true, ...fields } } });
}

function run(argv: string[], runEnv: Record<string, string> = {}) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: (text: string) => (stderr += text) },
    env: runEnv,
  });
  return { status, stdout, stderr };
}

test("a flag may carry an expiry date", () => {
  for (const expires of ["2026-12-31", "2028-02-29", "2027-01-01"]) {
    const config = flagWith({ expires });
    assert.equal(evaluate(config, "promo-banner", {}, { env, today: "2026-06-01" }).reason, "everyone", expires);
  }
});

test("an expiry that is not a real YYYY-MM-DD date is a config error naming the flag", () => {
  for (const expires of ["2026-13-01", "2026-02-30", "2027-02-29", "2026-2-3", "31/12/2026", "2026-12-31T00:00:00Z", "", 20261231, true]) {
    assert.throws(
      () => flagWith({ expires }),
      (error: unknown) => error instanceof ConfigError && /flag "promo-banner"/.test(error.message),
      String(expires),
    );
  }
});

test("other unknown flag fields are still rejected", () => {
  assert.throws(() => flagWith({ expires: "2026-12-31", owner: "growth" }), /unknown field "owner"/);
});

test("a flag is off with reason expired from the day after its expiry date", () => {
  const config = flagWith({ expires: "2026-04-30" });
  assert.equal(evaluate(config, "promo-banner", {}, { env, today: "2026-04-29" }).enabled, true);
  assert.equal(evaluate(config, "promo-banner", {}, { env, today: "2026-04-30" }).reason, "everyone");
  for (const today of ["2026-05-01", "2026-12-31", "2031-01-01"]) {
    const result = evaluate(config, "promo-banner", {}, { env, today });
    assert.equal(result.enabled, false, today);
    assert.equal(result.reason, "expired", today);
    assert.equal(result.flag, "promo-banner");
  }
});

test("expiry also stops a flag whose rules would match", () => {
  const config = flagWith({ expires: "2026-04-30", rules: [{ type: "allowlist", values: ["qa-anna"] }] });
  assert.equal(evaluate(config, "promo-banner", { userId: "qa-anna" }, { env, today: "2026-04-30" }).reason, "allowlist:hit");
  assert.equal(evaluate(config, "promo-banner", { userId: "qa-anna" }, { env, today: "2026-05-01" }).reason, "expired");
});

test("an environment override still wins over expiry", () => {
  const config = flagWith({ expires: "2026-04-30" });
  const on = evaluate(config, "promo-banner", {}, { env: { FLAGKIT_PROMO_BANNER: "on" }, today: "2027-01-01" });
  assert.deepEqual([on.enabled, on.reason], [true, "override:on"]);
  const off = evaluate(config, "promo-banner", {}, { env: { FLAGKIT_PROMO_BANNER: "off" }, today: "2026-01-01" });
  assert.deepEqual([off.enabled, off.reason], [false, "override:off"]);
});

test("the expiry check comes before the disabled check", () => {
  const config = parseConfig({ flags: { "promo-banner": { enabled: false, expires: "2026-04-30" } } });
  assert.equal(evaluate(config, "promo-banner", {}, { env, today: "2026-05-01" }).reason, "expired");
  assert.equal(evaluate(config, "promo-banner", {}, { env, today: "2026-04-30" }).reason, "disabled");
});

test("flags without an expiry never expire", () => {
  const config = parseConfig({ flags: { "dark-mode": { enabled: true } } });
  assert.equal(evaluate(config, "dark-mode", {}, { env, today: "2999-12-31" }).reason, "everyone");
});

test("today defaults to the current date", () => {
  const config = parseConfig({
    flags: { "old-promo": { enabled: true, expires: "2001-01-01" }, "far-future": { enabled: true, expires: "2999-12-31" } },
  });
  assert.equal(evaluate(config, "old-promo", {}, { env }).reason, "expired");
  assert.equal(evaluate(config, "far-future", {}, { env }).reason, "everyone");
});

test("flagkit eval takes --today", () => {
  assert.deepEqual(run(["eval", CONFIG, "spring-sale", "--today", "2026-04-30"]), { status: 0, stdout: "on (everyone)\n", stderr: "" });
  assert.deepEqual(run(["eval", CONFIG, "spring-sale", "--today", "2026-05-01"]), { status: 0, stdout: "off (expired)\n", stderr: "" });
  assert.equal(run(["eval", CONFIG, "beta-search", "--user", "qa-anna", "--today", "2027-01-15"]).stdout, "on (allowlist:hit)\n");
  assert.equal(run(["eval", CONFIG, "beta-search", "--today", "2027-01-16", "--user", "qa-anna"]).stdout, "off (expired)\n");
  assert.equal(run(["eval", CONFIG, "evergreen", "--today", "2999-01-01"]).stdout, "on (everyone)\n");
});

test("flagkit explain takes --today", () => {
  const expired = run(["explain", CONFIG, "beta-search", "--user", "qa-anna", "--today", "2027-01-16"]);
  assert.equal(expired.status, 0);
  assert.equal(expired.stdout.split("\n")[0], "beta-search: off (expired)");
  const live = run(["explain", CONFIG, "beta-search", "--user", "qa-anna", "--today", "2027-01-10"]);
  assert.equal(live.stdout.split("\n")[0], "beta-search: on (allowlist:hit)");
});

test("the command line keeps overrides and the current date", () => {
  assert.equal(run(["eval", CONFIG, "spring-sale", "--today", "2026-05-01"], { FLAGKIT_SPRING_SALE: "on" }).stdout, "on (override:on)\n");
  assert.equal(run(["eval", CONFIG, "old-promo"]).stdout, "off (expired)\n");
  assert.equal(run(["eval", CONFIG, "far-future"]).stdout, "on (everyone)\n");
});
