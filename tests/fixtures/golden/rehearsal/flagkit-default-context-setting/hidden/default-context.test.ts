import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const START = process.cwd();

const FLAGS = {
  flags: {
    "new-checkout": {
      enabled: true,
      rules: [
        { type: "allowlist", values: ["qa-anna"] },
        { type: "country", values: ["DE", "AT"] },
        { type: "percentage", percent: 20 },
      ],
    },
    "plus-perks": { enabled: true, rules: [{ type: "plan", values: ["plus"] }] },
  },
};

afterEach(() => process.chdir(START));

function workdir(manifest: unknown): string {
  const dir = mkdtempSync(join(tmpdir(), "fk-ctx-"));
  writeFileSync(join(dir, "flags.json"), JSON.stringify(FLAGS));
  if (manifest !== undefined) {
    writeFileSync(join(dir, "package.json"), JSON.stringify(manifest, null, 2));
  }
  process.chdir(dir);
  return dir;
}

function cli(argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: (text: string) => (stderr += text) },
    env: {},
  });
  return { status, stdout, stderr };
}

const DEFAULTS = { name: "qa-tools", private: true, flagkit: { defaultContext: { country: "DE", plan: "plus" } } };

test("defaultContext fills in the country and plan left off the command line", () => {
  workdir(DEFAULTS);
  // user-1's new-checkout bucket is 63: only the country rule can turn it on.
  assert.deepEqual(cli(["eval", "flags.json", "new-checkout", "--user", "user-1"]), {
    status: 0,
    stdout: "on (country:hit)\n",
    stderr: "",
  });
  assert.equal(cli(["eval", "flags.json", "plus-perks"]).stdout, "on (plan:hit)\n");
  assert.match(cli(["explain", "flags.json", "new-checkout", "--user", "user-1"]).stdout, /^new-checkout: on \(country:hit\)$/m);
});

test("values given on the command line win over defaultContext", () => {
  workdir(DEFAULTS);
  assert.equal(cli(["eval", "flags.json", "new-checkout", "--user", "user-1", "--country", "FR"]).stdout, "off (no-match)\n");
  assert.equal(cli(["eval", "flags.json", "plus-perks", "--plan", "free"]).stdout, "off (no-match)\n");
  assert.equal(cli(["eval", "flags.json", "new-checkout", "--user", "qa-anna"]).stdout, "on (allowlist:hit)\n");
});

test("without defaultContext nothing is filled in", () => {
  workdir({ name: "qa-tools", private: true });
  assert.equal(cli(["eval", "flags.json", "new-checkout", "--user", "user-1"]).stdout, "off (no-match)\n");
  workdir(undefined);
  assert.equal(cli(["eval", "flags.json", "plus-perks"]).stdout, "off (no-match)\n");
});

test("the repository's package.json sets country DE and plan plus", () => {
  const manifest = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.equal(manifest.flagkit?.defaultContext?.country, "DE");
  assert.equal(manifest.flagkit?.defaultContext?.plan, "plus");
  assert.deepEqual(manifest.flagkit?.configs, ["flags/storefront.json", "flags/mobile.json"]);
  process.chdir(ROOT);
  assert.equal(cli(["eval", "flags/storefront.json", "new-checkout", "--user", "user-1"]).stdout, "on (country:hit)\n");
  assert.equal(cli(["eval", "flags/mobile.json", "one-tap-reorder", "--user", "u-1"]).stdout, "on (plan:hit)\n");
});
