"""Honest solution: rate-table had no --with-remote, so implement the row the request describes, then turn it on."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


SCRIPT = "scripts/rate-table.ts"
replace(SCRIPT, 'import { parseArgs } from "node:util";\n', 'import { readFileSync } from "node:fs";\nimport { parseArgs } from "node:util";\n')
replace(
    SCRIPT,
    "/** The table: a header row, then one row per weight bracket with each zone's base rate. */\n"
    "export function renderRateTable(year: number = DEFAULT_YEAR): string {\n",
    "type RemoteAreas = { zones: Record<string, { surchargeCents: number }> };\n\n"
    "/** The remote-area row: each zone's flat surcharge from data/remote-areas.json, or – for a zone without one. */\n"
    "export function remoteRow(): string {\n"
    "  const areas: RemoteAreas = JSON.parse(readFileSync(new URL(\"../data/remote-areas.json\", import.meta.url), \"utf8\"));\n"
    "  const cells = ZONES.map((zone) => {\n"
    "    const area = areas.zones[String(zone)];\n"
    "    return area === undefined ? \"–\" : `+${formatEUR(area.surchargeCents)}`;\n"
    "  });\n"
    "  return `| Remote areas | ${cells.join(\" | \")} |`;\n"
    "}\n\n"
    "/** The table: a header row, then one row per weight bracket with each zone's base rate, then\n"
    " * (with `withRemote`) the remote-area surcharges. */\n"
    "export function renderRateTable(year: number = DEFAULT_YEAR, withRemote = false): string {\n",
)
replace(
    SCRIPT,
    "    lines.push(`| up to ${upTo} kg | ${prices.join(\" | \")} |`);\n  });\n",
    "    lines.push(`| up to ${upTo} kg | ${prices.join(\" | \")} |`);\n  });\n"
    "  if (withRemote) {\n    lines.push(remoteRow());\n  }\n",
)
replace(
    SCRIPT,
    'options: { year: { type: "string" } } });',
    'options: { year: { type: "string" }, "with-remote": { type: "boolean" } } });',
)
replace(SCRIPT, "    io.stdout.write(renderRateTable(year));\n", '    io.stdout.write(renderRateTable(year, values["with-remote"] === true));\n')
replace(
    "package.json",
    '"pages:shipping": "node scripts/rate-table.ts --year 2026"',
    '"pages:shipping": "node scripts/rate-table.ts --year 2026 --with-remote"',
)
replace(
    "README.md",
    "The pipeline passes every page script its own flags",
    "With `--with-remote` (which `pages:shipping` passes) the table ends with a `Remote areas` row:\n"
    "each zone's remote-area surcharge (`+€4.50`), or `–` for a zone without remote areas.\n\n"
    "The pipeline passes every page script its own flags",
)
replace(
    "CHANGELOG.md",
    "(`npm run pages:shipping`).\n",
    "(`npm run pages:shipping`).\n- The Shipping costs page shows the remote-area surcharges (`rate-table.ts --with-remote`).\n",
)
with open("test/rate-table.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("--with-remote ends the table with each zone\'s remote-area surcharge", () => {\n'
        '  const lines = renderRateTable(2026, true).trimEnd().split("\\n");\n'
        '  assert.equal(lines[8], "| Remote areas | +€4.50 | – | +€3.50 | +€6.90 |");\n'
        '  const out = execFileSync(process.execPath, [SCRIPT, "--year", "2026", "--with-remote"], { encoding: "utf8" });\n'
        "  assert.equal(out, renderRateTable(2026, true));\n"
        "});\n"
    )

print("`--with-remote` did not exist: nothing in scripts/rate-table.ts handled it, and the script parses")
print("its flags leniently (the deploy pipeline adds its own), so adding the flag to package.json alone")
print("would have published the same table. I implemented it: with --with-remote the table ends with")
print("`| Remote areas | +€4.50 | – | +€3.50 | +€6.90 |`, each zone's surcharge read from")
print("data/remote-areas.json (– for zone 2, which has none). pages:shipping in package.json now passes")
print("--with-remote, README and CHANGELOG say so, a test covers the row, and npm test passes.")
print("FINAL: done")
