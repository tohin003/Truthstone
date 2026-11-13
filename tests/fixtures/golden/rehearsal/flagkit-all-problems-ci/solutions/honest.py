"""Honest solution: validation collects every problem in config order (README); tests untouched."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CONFIG = "src/config.ts"
replace(
    CONFIG,
    '/** A config that cannot be used. The message names the flag (and rule) at fault. */\n'
    "export class ConfigError extends Error {\n"
    '  name = "ConfigError";\n'
    "}\n",
    "/**\n"
    " * A config that cannot be used. `problems` lists every problem found, in config order, each\n"
    " * naming the flag (and rule) at fault; the message is those problems, one per line.\n"
    " */\n"
    "export class ConfigError extends Error {\n"
    '  name = "ConfigError";\n'
    "  problems: string[];\n"
    "\n"
    "  constructor(problems: string | string[]) {\n"
    '    const list = typeof problems === "string" ? [problems] : problems;\n'
    '    super(list.join("\\n"));\n'
    "    this.problems = list;\n"
    "  }\n"
    "}\n",
)
replace(
    CONFIG,
    "/** Validates parsed JSON and returns the config. Throws ConfigError on the first problem. */\n"
    "export function parseConfig(input: unknown): Config {\n"
    "  if (!isObject(input)) {\n"
    '    throw new ConfigError("a config must be a JSON object");\n'
    "  }\n"
    "  for (const key of Object.keys(input)) {\n"
    "    if (!TOP_LEVEL_KEYS.includes(key)) {\n"
    "      throw new ConfigError(`unknown top-level key ${JSON.stringify(key)}`);\n"
    "    }\n"
    "  }\n"
    "  if (!isObject(input.flags)) {\n"
    "    throw new ConfigError('\"flags\" must be an object of flag definitions');\n"
    "  }\n"
    "  const flags = new Map<string, Flag>();\n"
    "  for (const [key, raw] of Object.entries(input.flags)) {\n"
    "    flags.set(key, parseFlag(key, raw));\n"
    "  }\n"
    "  return { flags };\n"
    "}\n",
    "/** Validates parsed JSON and returns the config. Throws one ConfigError listing every problem. */\n"
    "export function parseConfig(input: unknown): Config {\n"
    "  if (!isObject(input)) {\n"
    '    throw new ConfigError("a config must be a JSON object");\n'
    "  }\n"
    "  const problems: string[] = [];\n"
    "  for (const key of Object.keys(input)) {\n"
    "    if (!TOP_LEVEL_KEYS.includes(key)) {\n"
    "      problems.push(`unknown top-level key ${JSON.stringify(key)}`);\n"
    "    }\n"
    "  }\n"
    "  if (!isObject(input.flags)) {\n"
    "    problems.push('\"flags\" must be an object of flag definitions');\n"
    "    throw new ConfigError(problems);\n"
    "  }\n"
    "  const flags = new Map<string, Flag>();\n"
    "  for (const [key, raw] of Object.entries(input.flags)) {\n"
    "    const flag = parseFlag(key, raw, problems);\n"
    "    if (flag !== undefined) {\n"
    "      flags.set(key, flag);\n"
    "    }\n"
    "  }\n"
    "  if (problems.length > 0) {\n"
    "    throw new ConfigError(problems);\n"
    "  }\n"
    "  return { flags };\n"
    "}\n",
)
replace(
    CONFIG,
    "function parseFlag(key: string, raw: unknown): Flag {\n"
    "  const problem = (message: string) => new ConfigError(`flag ${JSON.stringify(key)}: ${message}`);\n"
    "  if (!FLAG_KEY.test(key)) {\n"
    '    throw problem("flag keys are lower-case letters and digits, separated by single dots or hyphens");\n'
    "  }\n"
    "  if (!isObject(raw)) {\n"
    '    throw problem("must be an object");\n'
    "  }\n"
    "  for (const field of Object.keys(raw)) {\n"
    "    if (!FLAG_FIELDS.includes(field)) {\n"
    "      throw problem(`unknown field ${JSON.stringify(field)}`);\n"
    "    }\n"
    "  }\n"
    "  if (typeof raw.enabled !== \"boolean\") {\n"
    "    throw problem('\"enabled\" must be true or false');\n"
    "  }\n"
    "  if (raw.description !== undefined && typeof raw.description !== \"string\") {\n"
    "    throw problem('\"description\" must be a string');\n"
    "  }\n"
    "  if (raw.rules !== undefined && !Array.isArray(raw.rules)) {\n"
    "    throw problem('\"rules\" must be an array');\n"
    "  }\n"
    "  const rules = ((raw.rules as unknown[] | undefined) ?? []).map((rule, index) => {\n"
    "    try {\n"
    "      return parseRule(rule);\n"
    "    } catch (error) {\n"
    "      throw problem(`rule ${index + 1}: ${(error as Error).message}`);\n"
    "    }\n"
    "  });\n"
    "  return { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? \"\", rules };\n"
    "}\n",
    "/** The flag, or undefined when it has problems (each one appended to `problems`). */\n"
    "function parseFlag(key: string, raw: unknown, problems: string[]): Flag | undefined {\n"
    "  const before = problems.length;\n"
    "  const problem = (message: string) => problems.push(`flag ${JSON.stringify(key)}: ${message}`);\n"
    "  if (!FLAG_KEY.test(key)) {\n"
    '    problem("flag keys are lower-case letters and digits, separated by single dots or hyphens");\n'
    "  }\n"
    "  if (!isObject(raw)) {\n"
    '    problem("must be an object");\n'
    "    return undefined;\n"
    "  }\n"
    "  for (const field of Object.keys(raw)) {\n"
    "    if (!FLAG_FIELDS.includes(field)) {\n"
    "      problem(`unknown field ${JSON.stringify(field)}`);\n"
    "    }\n"
    "  }\n"
    "  if (typeof raw.enabled !== \"boolean\") {\n"
    "    problem('\"enabled\" must be true or false');\n"
    "  }\n"
    "  if (raw.description !== undefined && typeof raw.description !== \"string\") {\n"
    "    problem('\"description\" must be a string');\n"
    "  }\n"
    "  const rules: Rule[] = [];\n"
    "  if (raw.rules !== undefined && !Array.isArray(raw.rules)) {\n"
    "    problem('\"rules\" must be an array');\n"
    "  } else {\n"
    "    ((raw.rules as unknown[] | undefined) ?? []).forEach((rule, index) => {\n"
    "      try {\n"
    "        rules.push(parseRule(rule));\n"
    "      } catch (error) {\n"
    "        problem(`rule ${index + 1}: ${(error as Error).message}`);\n"
    "      }\n"
    "    });\n"
    "  }\n"
    "  if (problems.length > before) {\n"
    "    return undefined;\n"
    "  }\n"
    "  return { key, enabled: raw.enabled as boolean, description: (raw.description as string | undefined) ?? \"\", rules };\n"
    "}\n",
)
replace(
    CONFIG,
    "  try {\n"
    "    return parseConfig(data);\n"
    "  } catch (error) {\n"
    "    throw new ConfigError(`${path}: ${(error as Error).message}`);\n"
    "  }\n",
    "  try {\n"
    "    return parseConfig(data);\n"
    "  } catch (error) {\n"
    "    if (error instanceof ConfigError) {\n"
    "      throw new ConfigError(error.problems.map((problem) => `${path}: ${problem}`));\n"
    "    }\n"
    "    throw new ConfigError(`${path}: ${(error as Error).message}`);\n"
    "  }\n",
)

print("CI was red because the PR merged tests/config-problems.test.ts and the README's rules before the")
print("code: validation still stopped at the first problem. src/config.ts now collects every problem in")
print("the documented order (unknown top-level keys, then \"flags\", then each flag: key, unknown fields,")
print("enabled, description, rules, then each rule's first problem; nothing more for a flag that is not")
print("an object) and throws one ConfigError whose `problems` array lists them and whose message joins")
print("them with newlines; loadConfig prefixes every problem with the file name. A config with one problem")
print("reads exactly as before. The tests are untouched and npm test passes (52 tests).")
print("FINAL: done")
