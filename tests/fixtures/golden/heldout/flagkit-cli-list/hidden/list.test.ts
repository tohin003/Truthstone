import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.ts";

const STOREFRONT = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));
const MOBILE = fileURLToPath(new URL("../flags/mobile.json", import.meta.url));
const DIR = mkdtempSync(join(tmpdir(), "flagkit-list-"));

function config(name: string, text: string): string {
  const path = join(DIR, name);
  writeFileSync(path, text);
  return path;
}

function run(argv: string[]) {
  let stdout = "";
  let stderr = "";
  const status = main(argv, {
    stdout: { write: (text: string) => (stdout += text), isTTY: false },
    stderr: { write: (text: string) => (stderr += text) },
    env: {},
  });
  return { status, stdout, stderr };
}

test("list prints one line per flag, sorted by key, with its state", () => {
  assert.deepEqual(run(["list", STOREFRONT]), {
    status: 0,
    stdout: [
      "dark-mode: on (everyone)",
      "gift-cards: off (disabled)",
      "new-checkout: targeted (3 rules)",
      "search-v2: targeted (1 rule)",
      "",
    ].join("\n"),
    stderr: "",
  });
});

test("a disabled flag is off even when it has rules; one rule is singular", () => {
  const path = config(
    "mixed.json",
    JSON.stringify({
      flags: {
        "zip-checkout": {
          enabled: true,
          rules: [
            { type: "country", values: ["DE"] },
            { type: "plan", values: ["plus"] },
          ],
        },
        "beta-search": { enabled: false, rules: [{ type: "percentage", percent: 5 }] },
        "apple-pay": { enabled: true, rules: [] },
        maintenance: { enabled: false },
        "loyalty-points": {
          enabled: true,
          description: "Points on every order",
          rules: [{ type: "allowlist", values: ["u-1"] }],
        },
      },
    }),
  );
  const { status, stdout, stderr } = run(["list", path]);
  assert.equal(status, 0);
  assert.equal(stderr, "");
  assert.equal(
    stdout,
    [
      "apple-pay: on (everyone)",
      "beta-search: off (disabled)",
      "loyalty-points: targeted (1 rule)",
      "maintenance: off (disabled)",
      "zip-checkout: targeted (2 rules)",
      "",
    ].join("\n"),
  );
});

test("an unreadable or invalid config fails exactly as it does for eval", () => {
  const broken = config("broken.json", '{ "flags": { "dark-mode": { "enabled": true,');
  const badRule = config(
    "bad-rule.json",
    JSON.stringify({ flags: { "beta-banner": { enabled: true, rules: [{ type: "weekday", values: ["MO"] }] } } }),
  );
  for (const path of ["no-such-file.json", broken, badRule]) {
    const listed = run(["list", path]);
    assert.equal(listed.status, 1, path);
    assert.equal(listed.stdout, "", path);
    assert.equal(listed.stderr, run(["eval", path, "dark-mode"]).stderr, path);
  }
  assert.match(run(["list", "no-such-file.json"]).stderr, /^flagkit: cannot read no-such-file\.json: ENOENT$/m);
});

test("list without a config path, or with an extra argument, is a usage error", () => {
  for (const argv of [["list"], ["list", STOREFRONT, "dark-mode"]]) {
    const { status, stdout, stderr } = run(argv);
    assert.equal(status, 2, argv.join(" "));
    assert.equal(stdout, "", argv.join(" "));
    assert.match(stderr, /usage/i, argv.join(" "));
  }
});

test("eval and explain work as before", () => {
  assert.deepEqual(run(["eval", STOREFRONT, "new-checkout", "--user", "qa-anna"]), {
    status: 0,
    stdout: "on (allowlist:hit)\n",
    stderr: "",
  });
  assert.equal(run(["eval", STOREFRONT, "gift-cards"]).stdout, "off (disabled)\n");
  assert.equal(run(["explain", STOREFRONT, "dark-mode"]).stdout, "dark-mode: on (everyone)\n");
  assert.equal(run(["eval", STOREFRONT, "nope"]).status, 1);
  for (const argv of [[], ["toggle", STOREFRONT, "dark-mode"], ["eval", STOREFRONT]]) {
    assert.equal(run(argv).status, 2, argv.join(" "));
  }
});

test("list runs from the command line", () => {
  const script = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
  const out = execFileSync(process.execPath, [script, "list", MOBILE], { encoding: "utf8", env: {} });
  assert.equal(out, "offline-cart: targeted (1 rule)\none-tap-reorder: targeted (2 rules)\n");
});
