import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as flagkit from "../src/index.ts";

const path = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

test("the public API keeps everything but the kiosk helpers", () => {
  for (const name of ["ConfigError", "loadConfig", "parseConfig", "RULE_TYPES", "envName", "envOverride", "evaluate", "bucket", "fnv1a32", "MATCHERS", "matcherFor"]) {
    assert.ok(name in flagkit, name);
  }
  assert.ok(!("kioskContext" in flagkit) && !("isKioskId" in flagkit));
});

test("the kiosk files are gone and the other configs still load and evaluate", () => {
  assert.equal(existsSync(path("../flags/kiosk.json")), false);
  assert.equal(existsSync(path("../src/kiosk.ts")), false);
  const storefront = flagkit.loadConfig(path("../flags/storefront.json"));
  assert.equal(flagkit.evaluate(storefront, "new-checkout", { userId: "qa-anna" }, { env: {} }).reason, "allowlist:hit");
  const mobile = flagkit.loadConfig(path("../flags/mobile.json"));
  assert.equal(flagkit.evaluate(mobile, "one-tap-reorder", { plan: "plus" }, { env: {} }).reason, "plan:hit");
  assert.ok(flagkit.loadConfig(path("../test/fixtures/flags.json")).flags.size > 0);
});
