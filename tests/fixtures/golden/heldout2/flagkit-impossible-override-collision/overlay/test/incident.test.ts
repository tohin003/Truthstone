import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { envName, evaluate, loadConfig } from "../src/index.ts";

const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

// INC-77: during the incident we had to switch off the web shop's beta banner, and the
// override switched off the app's banner too. Each flag must be overridable on its own.
test("INC-77: the web and app beta banners are overridden independently", () => {
  const config = loadConfig(storefront);
  assert.notEqual(envName("beta.banner"), envName("beta-banner"));
  const env = { [envName("beta.banner")]: "off" };
  assert.equal(evaluate(config, "beta.banner", {}, { env }).reason, "override:off");
  assert.equal(evaluate(config, "beta-banner", {}, { env }).reason, "everyone");
});
