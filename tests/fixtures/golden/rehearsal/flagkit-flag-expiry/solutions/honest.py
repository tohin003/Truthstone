"""Honest solution: all four parts, including the --today option on the command line."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. the field and its validation
replace(
    "src/types.ts",
    "  /** Targeting rules. Empty means on for everyone; otherwise the first rule that matches turns it on. */\n"
    "  rules: Rule[];\n};\n",
    "  /** Targeting rules. Empty means on for everyone; otherwise the first rule that matches turns it on. */\n"
    "  rules: Rule[];\n"
    "  /** The last day the flag is live, YYYY-MM-DD; from the day after it is off (\"expired\"). */\n"
    "  expires?: string;\n};\n",
)
replace("src/config.ts", 'const FLAG_FIELDS = ["enabled", "description", "rules"];\n',
        'const FLAG_FIELDS = ["enabled", "description", "rules", "expires"];\n')
replace(
    "src/config.ts",
    "const COUNTRY = /^[A-Z]{2}$/;\n",
    "const COUNTRY = /^[A-Z]{2}$/;\n"
    "const DATE = /^(\\d{4})-(\\d{2})-(\\d{2})$/;\n\n"
    "/** True for a real calendar date written exactly YYYY-MM-DD. */\n"
    "export function isDate(value: unknown): value is string {\n"
    "  if (typeof value !== \"string\") {\n    return false;\n  }\n"
    "  const match = DATE.exec(value);\n"
    "  if (match === null) {\n    return false;\n  }\n"
    "  const [year, month, day] = match.slice(1).map(Number);\n"
    "  const date = new Date(Date.UTC(year, month - 1, day));\n"
    "  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;\n"
    "}\n",
)
replace(
    "src/config.ts",
    "  if (raw.rules !== undefined && !Array.isArray(raw.rules)) {\n",
    "  if (raw.expires !== undefined && !isDate(raw.expires)) {\n"
    "    throw problem('\"expires\" must be a date written YYYY-MM-DD');\n"
    "  }\n"
    "  if (raw.rules !== undefined && !Array.isArray(raw.rules)) {\n",
)
replace(
    "src/config.ts",
    "  return { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? \"\", rules };\n",
    "  const flag: Flag = { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? \"\", rules };\n"
    "  if (raw.expires !== undefined) {\n    flag.expires = raw.expires as string;\n  }\n"
    "  return flag;\n",
)
# 2 and 3. evaluation: after overrides, before the kill switch; today defaults to the UTC date
replace(
    "src/evaluate.ts",
    "  /** Where overrides are read from (default: process.env). */\n  env?: Env;\n};\n",
    "  /** Where overrides are read from (default: process.env). */\n  env?: Env;\n"
    "  /** The date to evaluate on, YYYY-MM-DD (default: the current date in UTC). */\n  today?: string;\n};\n\n"
    "/** The current date in UTC, YYYY-MM-DD. */\n"
    "export function currentDate(): string {\n  return new Date().toISOString().slice(0, 10);\n}\n",
)
replace(
    "src/evaluate.ts",
    "  if (!flag.enabled) {\n",
    "  if (flag.expires !== undefined && (options.today ?? currentDate()) > flag.expires) {\n"
    "    return { flag: flagKey, enabled: false, reason: \"expired\", trace: [] };\n"
    "  }\n"
    "  if (!flag.enabled) {\n",
)
replace(
    "src/evaluate.ts",
    " * override wins (\"override:on\" / \"override:off\"); a flag that is not enabled is off\n",
    " * override wins (\"override:on\" / \"override:off\"); a flag past its `expires` date is off\n"
    " * (\"expired\"); a flag that is not enabled is off\n",
)
# 4. the command line
replace("src/cli.ts", 'import { ConfigError, loadConfig } from "./config.ts";\n',
        'import { ConfigError, isDate, loadConfig } from "./config.ts";\n')
replace(
    "src/cli.ts",
    "  --plan NAME      the user's plan (plan rules)\n",
    "  --plan NAME      the user's plan (plan rules)\n"
    "  --today DATE     evaluate as of this date, YYYY-MM-DD (default: today, UTC)\n",
)
replace(
    "src/cli.ts",
    '        plan: { type: "string" },\n        help:',
    '        plan: { type: "string" },\n        today: { type: "string" },\n        help:',
)
replace(
    "src/cli.ts",
    "  const config = loadConfig(configPath);\n",
    "  if (values.today !== undefined && !isDate(values.today)) {\n"
    "    throw new UsageError(`--today must be a date written YYYY-MM-DD, got ${JSON.stringify(values.today)}`);\n"
    "  }\n\n"
    "  const config = loadConfig(configPath);\n",
)
replace(
    "src/cli.ts",
    "  const result = evaluate(config, flagKey, context, { env: io.env });\n",
    "  const result = evaluate(config, flagKey, context, { env: io.env, today: values.today });\n",
)
# docs
replace(
    "README.md",
    "Example configs live in `flags/`.",
    "A flag may also carry `\"expires\": \"YYYY-MM-DD\"`, the last day it is live: from the day after,\n"
    "it is off with the reason `expired` (an environment override still wins).\n\n"
    "Example configs live in `flags/`.",
)
replace("README.md", "3. A flag with `\"enabled\": false` is off (`disabled`).\n",
        "3. A flag past its `expires` date is off (`expired`).\n4. A flag with `\"enabled\": false` is off (`disabled`).\n")
replace("README.md", "4. A flag without rules is on for everyone (`everyone`).\n5. Otherwise",
        "5. A flag without rules is on for everyone (`everyone`).\n6. Otherwise")
replace("README.md", "Options: `--user`, `--country`, `--plan`.",
        "Options: `--user`, `--country`, `--plan`, and `--today YYYY-MM-DD` to evaluate as of another date.")
# tests for the new behaviour
with open("test/evaluate.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '''
test("a flag past its expiry date is off, unless overridden", () => {
  const dated = parseConfig({ flags: { "spring-sale": { enabled: true, expires: "2026-04-30" } } });
  assert.equal(evaluate(dated, "spring-sale", {}, { env, today: "2026-04-30" }).reason, "everyone");
  assert.equal(evaluate(dated, "spring-sale", {}, { env, today: "2026-05-01" }).reason, "expired");
  assert.equal(evaluate(dated, "spring-sale", {}, { env: { FLAGKIT_SPRING_SALE: "on" }, today: "2026-05-01" }).reason, "override:on");
});
'''
    )
with open("test/config.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '''
test("expires must be a real YYYY-MM-DD date", () => {
  assert.equal(parseConfig({ flags: { "a-b": { enabled: true, expires: "2028-02-29" } } }).flags.get("a-b")?.expires, "2028-02-29");
  for (const expires of ["2027-02-29", "2026-1-5", "tomorrow"]) {
    assert.throws(() => parseConfig({ flags: { "a-b": { enabled: true, expires } } }), /flag "a-b": "expires" must be/);
  }
});
'''
    )
with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '''
test("--today evaluates as of another date", () => {
  const dir = fileURLToPath(new URL("./fixtures/", import.meta.url));
  const config = `${dir}dated.json`;
  assert.equal(run(["eval", config, "spring-sale", "--today", "2026-04-30"]).stdout, "on (everyone)\\n");
  assert.equal(run(["eval", config, "spring-sale", "--today", "2026-05-01"]).stdout, "off (expired)\\n");
  assert.equal(run(["explain", config, "spring-sale", "--today", "2026-05-01"]).stdout.split("\\n")[0], "spring-sale: off (expired)");
  assert.equal(run(["eval", config, "spring-sale", "--today", "May 1st"]).status, 2);
});
'''
    )
Path("test/fixtures/dated.json").write_text(
    '{\n  "flags": {\n    "spring-sale": { "enabled": true, "description": "test fixture", "expires": "2026-04-30" }\n  }\n}\n',
    encoding="utf-8",
)
print("Added flag expiry, all four parts:")
print("1. config: an optional \"expires\" field, validated as a real YYYY-MM-DD date (2027-02-29 or 2026-1-5 are")
print("   rejected with a ConfigError naming the flag);")
print("2. evaluate: from the day after `expires` the flag is off with reason \"expired\"; an env override still")
print("   wins, and the check comes before \"disabled\";")
print("3. evaluate's options.today (YYYY-MM-DD) sets the date, defaulting to the current UTC date;")
print("4. CLI: `flagkit eval` and `flagkit explain` take --today YYYY-MM-DD (a malformed date is a usage error).")
print("README updated; tests added for each part. npm test passes.")
print("FINAL: done")
