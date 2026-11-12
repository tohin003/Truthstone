import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";
import { ConfigError, parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

function configWith(values: unknown[]) {
  return parseConfig({ flags: { "eu-promo": { enabled: true, rules: [{ type: "country", values }] } } });
}

test("country codes in a config are accepted in any case", () => {
  assert.doesNotThrow(() => configWith(["de", "At", "NL"]));
});

test("lower- and mixed-case config codes match contexts in any case", () => {
  const config = configWith(["de", "At"]);
  for (const country of ["DE", "de", "AT", "at"]) {
    const result = evaluate(config, "eu-promo", { country }, { env: {} });
    assert.equal(result.enabled, true, country);
    assert.equal(result.reason, "country:hit", country);
  }
  assert.equal(evaluate(config, "eu-promo", { country: "FR" }, { env: {} }).reason, "no-match");
  assert.equal(evaluate(config, "eu-promo", {}, { env: {} }).reason, "no-match");
});

test("upper-case config codes behave as before", () => {
  const config = configWith(["DE"]);
  assert.equal(evaluate(config, "eu-promo", { country: "de" }, { env: {} }).reason, "country:hit");
  assert.equal(evaluate(config, "eu-promo", { country: "AT" }, { env: {} }).reason, "no-match");
});

test("codes that are not two letters are still rejected", () => {
  for (const bad of ["DEU", "d", "1A", ""]) {
    assert.throws(() => configWith([bad]), (error: unknown) => error instanceof ConfigError, bad);
  }
});

test("the marketing config's lower-case codes work through the CLI", () => {
  let stdout = "";
  const status = main(["eval", fileURLToPath(new URL("../flags/marketing.json", import.meta.url)), "eu-banner", "--country", "DE"], {
    stdout: { write: (text: string) => (stdout += text) },
    stderr: { write: () => true },
    env: {},
  });
  assert.equal(status, 0);
  assert.equal(stdout, "on (country:hit)\n");
});
