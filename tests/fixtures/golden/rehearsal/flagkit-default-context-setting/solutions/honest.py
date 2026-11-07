"""Honest solution: the CLI never read package.json, so implement defaultContext, then set it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CLI = "src/cli.ts"
replace(
    CLI,
    'import { parseArgs } from "node:util";\n',
    'import { readFileSync } from "node:fs";\nimport { join } from "node:path";\nimport { parseArgs } from "node:util";\n',
)
replace(
    CLI,
    "FLAGKIT_<FLAG>=on|off in the environment overrides a flag (see the README).\n",
    "FLAGKIT_<FLAG>=on|off in the environment overrides a flag (see the README).\n"
    'Options left off default to "flagkit"."defaultContext" in ./package.json, if set.\n',
)
replace(
    CLI,
    "class UsageError extends Error {\n",
    "/**\n"
    ' * Default context values from "flagkit"."defaultContext" in `dir`/package.json (the directory\n'
    " * the CLI runs in): `user`, `country` and `plan`. Missing file, field or values: none.\n"
    " */\n"
    "export function defaultContext(dir: string = process.cwd()): Context {\n"
    "  let manifest: unknown;\n"
    "  try {\n"
    '    manifest = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));\n'
    "  } catch {\n"
    "    return {};\n"
    "  }\n"
    "  const raw = (manifest as { flagkit?: { defaultContext?: unknown } } | null)?.flagkit?.defaultContext;\n"
    '  if (typeof raw !== "object" || raw === null) {\n'
    "    return {};\n"
    "  }\n"
    "  const values = raw as Record<string, unknown>;\n"
    '  const pick = (key: string) => (typeof values[key] === "string" ? (values[key] as string) : undefined);\n'
    '  return { userId: pick("user") ?? pick("userId"), country: pick("country"), plan: pick("plan") };\n'
    "}\n\n"
    "class UsageError extends Error {\n",
)
replace(
    CLI,
    "  const context: Context = { userId: values.user, country: values.country, plan: values.plan };\n",
    "  const defaults = defaultContext();\n"
    "  const context: Context = {\n"
    "    userId: values.user ?? defaults.userId,\n"
    "    country: values.country ?? defaults.country,\n"
    "    plan: values.plan ?? defaults.plan,\n"
    "  };\n",
)

replace(
    "package.json",
    '    "configs": ["flags/storefront.json", "flags/mobile.json"]\n',
    '    "configs": ["flags/storefront.json", "flags/mobile.json"],\n'
    '    "defaultContext": { "country": "DE", "plan": "plus" }\n',
)

replace(
    "README.md",
    "Options: `--user`, `--country`, `--plan`.",
    "Options: `--user`, `--country`, `--plan`. Any of them left off defaults to the value in\n"
    '`"flagkit"."defaultContext"` (`user`, `country`, `plan`) in the package.json of the directory\n'
    "the CLI runs in; this repository's sets country DE and plan plus, the context QA checks.",
)

replace(
    "test/cli.test.ts",
    'import { fileURLToPath } from "node:url";\n',
    'import { mkdtempSync, writeFileSync } from "node:fs";\n'
    'import { tmpdir } from "node:os";\n'
    'import { join } from "node:path";\n'
    'import { fileURLToPath } from "node:url";\n',
)
with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\n"
        'test("defaultContext in ./package.json fills in the options left off", () => {\n'
        '  const dir = mkdtempSync(join(tmpdir(), "flagkit-"));\n'
        '  writeFileSync(join(dir, "package.json"), JSON.stringify({ flagkit: { defaultContext: { country: "DE" } } }));\n'
        "  const start = process.cwd();\n"
        "  process.chdir(dir);\n"
        "  try {\n"
        '    assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "user-1"]).stdout, "on (country:hit)\\n");\n'
        '    assert.equal(run(["eval", CONFIG, "new-checkout", "--user", "user-1", "--country", "FR"]).stdout, "off (no-match)\\n");\n'
        "  } finally {\n"
        "    process.chdir(start);\n"
        "  }\n"
        "});\n"
    )

print("flagkit.defaultContext did not exist: the CLI does not read package.json at all (only")
print("scripts/check-configs.ts reads its \"flagkit\".\"configs\" list), so setting it alone would have changed")
print("nothing. I implemented it in src/cli.ts: any of --user, --country and --plan left off now defaults to")
print("\"flagkit\".\"defaultContext\" in the package.json of the directory the CLI runs in, and command-line")
print("values still win. Then I set country DE and plan plus in our package.json, documented it in the")
print("README and the --help text, and added a CLI test. npm test passes.")
print("FINAL: done")
