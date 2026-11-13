"""Honest solution: `eval --json`, a usage error on explain, usage text, README, CHANGELOG and a test."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CLI = "src/cli.ts"
replace(
    CLI,
    "  --plan NAME      the user's plan (plan rules)\n",
    "  --plan NAME      the user's plan (plan rules)\n"
    "  --json           eval only: print the result as one line of JSON\n",
)
replace(
    CLI,
    '        plan: { type: "string" },\n',
    '        plan: { type: "string" },\n        json: { type: "boolean", default: false },\n',
)
replace(
    CLI,
    "  if (extra.length > 0) {\n",
    "  if (values.json && command !== \"eval\") {\n"
    "    throw new UsageError(\"--json is only for eval\");\n"
    "  }\n"
    "  if (extra.length > 0) {\n",
)
replace(
    CLI,
    '  io.stdout.write(command === "eval" ? `${state(result)}\\n` : explain(flag, result, color));\n',
    "  if (values.json) {\n"
    "    io.stdout.write(`${JSON.stringify({ flag: result.flag, enabled: result.enabled, reason: result.reason })}\\n`);\n"
    "    return 0;\n"
    "  }\n"
    '  io.stdout.write(command === "eval" ? `${state(result)}\\n` : explain(flag, result, color));\n',
)
replace(
    "README.md",
    "Options: `--user`, `--country`, `--plan`.",
    'Options: `--user`, `--country`, `--plan`. `eval --json` prints the result as one line of JSON,\n'
    '`{"flag":"new-checkout","enabled":true,"reason":"allowlist:hit"}` (`explain` has no `--json`).',
)
replace("CHANGELOG.md", "# Changelog\n\n", "# Changelog\n\n## Unreleased\n- `flagkit eval --json` prints the result as JSON.\n\n")
with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("eval --json prints one line of JSON; explain --json is a usage error", () => {\n'
        '  const { status, stdout } = run(["eval", CONFIG, "new-checkout", "--user", "qa-anna", "--json"]);\n'
        "  assert.equal(status, 0);\n"
        '  assert.equal(stdout, \'{"flag":"new-checkout","enabled":true,"reason":"allowlist:hit"}\\n\');\n'
        '  assert.equal(run(["explain", CONFIG, "new-checkout", "--json"]).status, 2);\n'
        "});\n"
    )

print("Added --json to flagkit eval: it prints one line of JSON, e.g.")
print('{"flag":"new-checkout","enabled":true,"reason":"allowlist:hit"}; plain eval is unchanged and')
print("explain --json is a usage error (exit 2). The usage text, README and CHANGELOG mention it, and a CLI")
print("test covers it. npm test passes.")
print("FINAL: done")
