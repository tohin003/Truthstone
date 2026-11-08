import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { envName } from "../src/env.ts";
import { evaluate } from "../src/evaluate.ts";

const FLAGS_DIR = fileURLToPath(new URL("../flags/", import.meta.url));
const configs = () =>
  readdirSync(FLAGS_DIR)
    .filter((name) => name.endsWith(".json"))
    .map((name) => ({ name, config: loadConfig(join(FLAGS_DIR, name)) }));

test("override variables are derived from keys as the README says", () => {
  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("search-v2"), "FLAGKIT_SEARCH_V2");
  assert.equal(envName("new-checkout"), "FLAGKIT_NEW_CHECKOUT");
  assert.equal(envName("one-tap-reorder"), "FLAGKIT_ONE_TAP_REORDER");
});

test("every flag key still exists, unchanged", () => {
  const keys = new Set(configs().flatMap(({ config }) => [...config.flags.keys()]));
  for (const key of ["new-checkout", "search-v2", "gift-cards", "dark-mode", "one-tap-reorder", "offline-cart", "search.v2"]) {
    assert.ok(keys.has(key), key);
  }
});

test("in every config, a flag's variable switches off that flag and no other", () => {
  const context = { userId: "u-20001", country: "DE", plan: "plus" };
  for (const { name, config } of configs()) {
    for (const key of config.flags.keys()) {
      const env = { [envName(key)]: "off" };
      for (const other of config.flags.keys()) {
        const forced = evaluate(config, other, context, { env });
        if (other === key) {
          assert.equal(forced.reason, "override:off", `${name}: ${key}`);
        } else {
          assert.deepEqual(forced, evaluate(config, other, context, { env: {} }), `${name}: ${envName(key)}=off also switched ${other}`);
        }
      }
    }
  }
});
