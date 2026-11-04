import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const rootUrl = new URL("../", import.meta.url);
const raw = {
  flags: {
    "priority-support": { enabled: true, rules: [{ type: "plan", values: ["plus", "business"] }] },
  },
};
const env = {};

const entries = [
  ["src/index.ts", "the sources"],
  ["dist/index.js", "dist/, which the services import"],
];

for (const [path, label] of entries) {
  test(`plan rules ignore case and surrounding spaces in ${label}`, async () => {
    const { parseConfig, evaluate } = await import(new URL(path, rootUrl).href);
    const config = parseConfig(raw);
    for (const plan of ["PLUS", "Plus", " business ", "BUSINESS", "plus"]) {
      const result = evaluate(config, "priority-support", { plan }, { env });
      assert.equal(result.enabled, true, `plan ${JSON.stringify(plan)}`);
      assert.equal(result.reason, "plan:hit", `plan ${JSON.stringify(plan)}`);
    }
  });

  test(`other plans, and no plan at all, still miss in ${label}`, async () => {
    const { parseConfig, evaluate } = await import(new URL(path, rootUrl).href);
    const config = parseConfig(raw);
    for (const context of [{ plan: "FREE" }, { plan: "plus-trial" }, {}]) {
      const result = evaluate(config, "priority-support", context, { env });
      assert.equal(result.enabled, false, JSON.stringify(context));
      assert.equal(result.reason, "no-match", JSON.stringify(context));
    }
  });
}

test("dist/ is exactly what `npm run build` produces from src/ (CI's check-dist)", () => {
  const run = spawnSync(process.execPath, ["scripts/build.ts", "--check"], {
    cwd: fileURLToPath(rootUrl),
    encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stderr);
});
