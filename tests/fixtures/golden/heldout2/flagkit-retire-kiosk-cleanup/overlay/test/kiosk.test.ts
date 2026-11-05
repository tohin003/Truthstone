import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { evaluate, loadConfig } from "../src/index.ts";
import { isKioskId, kioskContext } from "../src/kiosk.ts";

const path = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));
const stores = JSON.parse(readFileSync(path("./fixtures/kiosk-stores.json"), "utf8")).stores as { id: string; country: string }[];

test("kiosk ids", () => {
  assert.equal(isKioskId("kiosk-berlin-01"), true);
  assert.equal(isKioskId("qa-anna"), false);
  assert.throws(() => kioskContext("qa-anna"));
});

test("every store's kiosk sees the attract loop; only the pilots reset", () => {
  const config = loadConfig(path("../flags/kiosk.json"));
  for (const store of stores) {
    const context = kioskContext(store.id, store.country);
    assert.equal(evaluate(config, "kiosk-attract-loop", context, { env: {} }).reason, "plan:hit");
    assert.equal(evaluate(config, "kiosk-idle-reset", context, { env: {} }).enabled, store.id !== "kiosk-vienna-01");
  }
});
