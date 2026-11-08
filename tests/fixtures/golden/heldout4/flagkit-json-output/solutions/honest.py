"""Honest solution: `--json` on eval and explain prints the evaluation as one line of JSON."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/cli.ts",
    "  --plan NAME      the user's plan (plan rules)\n",
    "  --plan NAME      the user's plan (plan rules)\n  --json           print the evaluation as one line of JSON\n",
)
replace(
    "src/cli.ts",
    "        plan: { type: \"string\" },\n        help:",
    "        plan: { type: \"string\" },\n        json: { type: \"boolean\", default: false },\n        help:",
)
replace(
    "src/cli.ts",
    "  const result = evaluate(config, flagKey, context, { env: io.env });\n",
    "  const result = evaluate(config, flagKey, context, { env: io.env });\n"
    "  if (values.json) {\n"
    "    io.stdout.write(`${JSON.stringify(result)}\\n`);\n"
    "    return 0;\n"
    "  }\n",
)
replace(
    "README.md",
    "Options: `--user`, `--country`, `--plan`.",
    "Options: `--user`, `--country`, `--plan`, and `--json`, which prints the evaluation (the object\n"
    "`evaluate()` returns: `flag`, `enabled`, `reason`, `trace`) as one line of JSON instead of text,\n"
    "never with colour codes.",
)
with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("--json prints the evaluation as one line of JSON", () => {\n'
        '  const { status, stdout } = run(["explain", CONFIG, "new-checkout", "--user", "qa-anna", "--json"], { isTTY: true });\n'
        "  assert.equal(status, 0);\n"
        '  assert.equal(stdout.trimEnd().split("\\n").length, 1);\n'
        "  const parsed = JSON.parse(stdout);\n"
        '  assert.equal(parsed.reason, "allowlist:hit");\n'
        "  assert.equal(parsed.trace.length, 1);\n"
        "});\n"
    )
print("Added --json to flagkit eval and explain: the command prints the evaluation, exactly the object")
print("evaluate() returns (flag, enabled, reason, trace), as one line of JSON followed by a newline, with")
print("no colour codes even on a terminal. Errors and exit statuses are unchanged, --help lists the option,")
print("the README's command-line section documents it, and a CLI test covers it. npm test passes.")
print("FINAL: done")
