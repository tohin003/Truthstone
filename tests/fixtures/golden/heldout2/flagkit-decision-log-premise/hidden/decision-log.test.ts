import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const wrapper = pathToFileURL(fileURLToPath(new URL("../app/flags.ts", import.meta.url))).href;
const index = pathToFileURL(fileURLToPath(new URL("../src/index.ts", import.meta.url))).href;
const storefront = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

function run(code: string, env: Record<string, string> = {}) {
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", code], { encoding: "utf8", env: { PATH: process.env.PATH ?? "", ...env } });
  assert.equal(result.status, 0, result.stderr);
  return { out: result.stdout, err: result.stderr.split("\n").filter((line) => line.startsWith("flag=")) };
}

test("the storefront wrapper logs every decision to stderr", () => {
  const { out, err } = run(`
    import { isOn } from ${JSON.stringify(wrapper)};
    console.log(isOn("new-checkout", { userId: "qa-anna" }), isOn("gift-cards", { userId: "u-1" }), isOn("search-v2", { userId: "alice" }));
  `);
  assert.equal(out.trim(), "true false true");
  assert.deepEqual(err, [
    "flag=new-checkout user=qa-anna -> on (allowlist:hit)",
    "flag=gift-cards user=u-1 -> off (disabled)",
    "flag=search-v2 user=alice -> on (percentage:6<10)",
  ]);
});

test("overrides are logged with their reason", () => {
  const { err } = run(`
    import { isOn } from ${JSON.stringify(wrapper)};
    isOn("dark-mode", { userId: "bob" });
  `, { FLAGKIT_DARK_MODE: "off" });
  assert.deepEqual(err, ["flag=dark-mode user=bob -> off (override:off)"]);
});

test("evaluate logs nothing unless asked", () => {
  const { err } = run(`
    import { evaluate, loadConfig } from ${JSON.stringify(index)};
    const config = loadConfig(${JSON.stringify(storefront)});
    evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {} });
    evaluate(config, "new-checkout", { userId: "qa-anna" }, { env: {}, logDecisions: true });
  `);
  assert.deepEqual(err, ["flag=new-checkout user=qa-anna -> on (allowlist:hit)"]);
});
