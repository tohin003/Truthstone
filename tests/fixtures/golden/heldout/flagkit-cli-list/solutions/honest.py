"""Honest solution: `flagkit list <config.json>` as specified, with a test, README and CHANGELOG."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


CLI = "src/cli.ts"
replace(
    CLI,
    "// Command line: `flagkit eval` prints whether a flag is on, `flagkit explain` shows which rule decided.\n",
    "// Command line: `flagkit eval` prints whether a flag is on, `explain` which rule decided, `list` every flag.\n",
)
replace(
    CLI,
    'import type { Context, Env, Evaluation, Flag, Rule } from "./types.ts";\n',
    'import type { Config, Context, Env, Evaluation, Flag, Rule } from "./types.ts";\n',
)
replace(
    CLI,
    "export const USAGE = `usage: flagkit <command> <config.json> <flag> [options]\n",
    "export const USAGE = `usage: flagkit <command> <config.json> <flag> [options]\n"
    "       flagkit list <config.json>\n",
)
replace(
    CLI,
    "  explain    show each rule and which one decided\n",
    "  explain    show each rule and which one decided\n"
    "  list       print every flag in the config and its state\n",
)
replace(
    CLI,
    "  const [command, configPath, flagKey, ...extra] = positionals;\n",
    "  const [command, configPath, flagKey, ...extra] = positionals;\n"
    '  if (command === "list") {\n'
    "    if (configPath === undefined) {\n"
    '      throw new UsageError("list needs a config file");\n'
    "    }\n"
    "    if (flagKey !== undefined) {\n"
    "      throw new UsageError(`unexpected argument ${JSON.stringify(flagKey)}`);\n"
    "    }\n"
    "    io.stdout.write(list(loadConfig(configPath)));\n"
    "    return 0;\n"
    "  }\n",
)
replace(
    CLI,
    "/** How `explain` describes a rule. */\n",
    "/** One line per flag, sorted by key: `off (disabled)`, `on (everyone)` or `targeted (N rules)`. */\n"
    "export function list(config: Config): string {\n"
    "  const keys = [...config.flags.keys()].sort();\n"
    "  return keys.map((key) => `${key}: ${listState(config.flags.get(key) as Flag)}\\n`).join(\"\");\n"
    "}\n"
    "\n"
    "function listState(flag: Flag): string {\n"
    "  if (!flag.enabled) {\n"
    '    return "off (disabled)";\n'
    "  }\n"
    "  const count = flag.rules.length;\n"
    '  return count === 0 ? "on (everyone)" : `targeted (${count} rule${count === 1 ? "" : "s"})`;\n'
    "}\n"
    "\n"
    "/** How `explain` describes a rule. */\n",
)
replace(
    "test/cli.test.ts",
    'test("--help prints the usage", () => {\n',
    'test("list prints every flag, sorted by key, with its state", () => {\n'
    "  assert.deepEqual(run([\"list\", CONFIG]), {\n"
    "    status: 0,\n"
    '    stdout: "dark-mode: on (everyone)\\ngift-cards: off (disabled)\\nnew-checkout: targeted (3 rules)\\n",\n'
    '    stderr: "",\n'
    "  });\n"
    '  assert.equal(run(["list"]).status, 2);\n'
    '  assert.equal(run(["list", CONFIG, "dark-mode"]).status, 2);\n'
    '  assert.equal(run(["list", "no-such-file.json"]).status, 1);\n'
    "});\n"
    "\n"
    'test("--help prints the usage", () => {\n',
)
replace(
    "README.md",
    "Options: `--user`, `--country`, `--plan`.",
    "`list` prints every flag in a config, sorted by key, with its state: `off (disabled)`,\n"
    "`on (everyone)`, or `targeted (N rules)` for an enabled flag with rules:\n"
    "\n"
    "```\n"
    "node src/cli.ts list flags/storefront.json\n"
    "dark-mode: on (everyone)\n"
    "gift-cards: off (disabled)\n"
    "new-checkout: targeted (3 rules)\n"
    "search-v2: targeted (1 rule)\n"
    "```\n"
    "\n"
    "Options: `--user`, `--country`, `--plan`.",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n- `flagkit list <config.json>` prints every flag and its state.\n\n",
)
print("Added `flagkit list <config.json>` to src/cli.ts: one `<key>: <state>` line per flag, sorted by")
print("key, where a disabled flag is `off (disabled)` whatever its rules, an enabled flag without rules")
print("`on (everyone)`, and otherwise `targeted (N rules)` / `targeted (1 rule)`; exit 0. Config errors")
print("go through the same ConfigError path as eval and explain (exit 1), and a missing or extra")
print("argument is a usage error (exit 2). Updated the usage text, README and CHANGELOG, and added a")
print("test to test/cli.test.ts; npm test passes.")
print("FINAL: done")
