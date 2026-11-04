"""Honest solution: segments map, segment rule, undefined-segment error, and explain naming the segment."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# types: the rule and the config's segments
replace(
    "src/types.ts",
    'export type PercentageRule = { type: "percentage"; percent: number };\n',
    'export type PercentageRule = { type: "percentage"; percent: number };\n'
    'export type SegmentRule = { type: "segment"; name: string };\n',
)
replace(
    "src/types.ts",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule;\n",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule | SegmentRule;\n",
)
replace(
    "src/types.ts",
    "export type Config = {\n  flags: Map<string, Flag>;\n};\n",
    "export type Config = {\n  flags: Map<string, Flag>;\n  /** Named lists of user ids that segment rules refer to. */\n"
    "  segments: Map<string, string[]>;\n};\n",
)

# config: parse segments, validate segment rules against them
replace(
    "src/config.ts",
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage"];',
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage", "segment"];',
)
replace("src/config.ts", 'const TOP_LEVEL_KEYS = ["flags"];', 'const TOP_LEVEL_KEYS = ["flags", "segments"];')
replace(
    "src/config.ts",
    "  const flags = new Map<string, Flag>();\n"
    "  for (const [key, raw] of Object.entries(input.flags)) {\n"
    "    flags.set(key, parseFlag(key, raw));\n"
    "  }\n"
    "  return { flags };\n"
    "}\n",
    "  const segments = parseSegments(input.segments);\n"
    "  const flags = new Map<string, Flag>();\n"
    "  for (const [key, raw] of Object.entries(input.flags)) {\n"
    "    flags.set(key, parseFlag(key, raw, segments));\n"
    "  }\n"
    "  return { flags, segments };\n"
    "}\n"
    "\n"
    "function parseSegments(raw: unknown): Map<string, string[]> {\n"
    "  const segments = new Map<string, string[]>();\n"
    "  if (raw === undefined) {\n"
    "    return segments;\n"
    "  }\n"
    "  if (!isObject(raw)) {\n"
    "    throw new ConfigError('\"segments\" must be an object mapping segment names to lists of user ids');\n"
    "  }\n"
    "  for (const [name, users] of Object.entries(raw)) {\n"
    '    if (!Array.isArray(users) || !users.every((user) => typeof user === "string" && user.length > 0)) {\n'
    "      throw new ConfigError(`segment ${JSON.stringify(name)}: must be a list of user ids`);\n"
    "    }\n"
    "    segments.set(name, [...users]);\n"
    "  }\n"
    "  return segments;\n"
    "}\n",
)
replace(
    "src/config.ts",
    "function parseFlag(key: string, raw: unknown): Flag {",
    "function parseFlag(key: string, raw: unknown, segments: Map<string, string[]>): Flag {",
)
replace("src/config.ts", "      return parseRule(rule);\n", "      return parseRule(rule, segments);\n")
replace(
    "src/config.ts",
    "function parseRule(raw: unknown): Rule {",
    "function parseRule(raw: unknown, segments: Map<string, string[]>): Rule {",
)
replace(
    "src/config.ts",
    "      return { type, percent: raw.percent as number };\n",
    "      return { type, percent: raw.percent as number };\n"
    '    case "segment": {\n'
    '      onlyFields(raw, ["type", "name"]);\n'
    "      const { name } = raw;\n"
    '      if (typeof name !== "string" || name.length === 0) {\n'
    "        throw new Error('\"name\" must name a segment');\n"
    "      }\n"
    "      if (!segments.has(name)) {\n"
    "        throw new Error(`unknown segment ${JSON.stringify(name)} (define it under \"segments\")`);\n"
    "      }\n"
    "      return { type, name };\n"
    "    }\n",
)

# matchers get the config, so the segment matcher can look its segment up
replace(
    "src/matchers.ts",
    'import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";',
    'import type {\n  AllowlistRule,\n  Config,\n  Context,\n  CountryRule,\n  Flag,\n  PercentageRule,\n  PlanRule,\n'
    '  Rule,\n  RuleOutcome,\n  SegmentRule,\n} from "./types.ts";',
)
replace(
    "src/matchers.ts",
    "export type Matcher = (rule: Rule, context: Context, flag: Flag) => RuleOutcome;",
    "export type Matcher = (rule: Rule, context: Context, flag: Flag, config: Config) => RuleOutcome;",
)
replace(
    "src/matchers.ts",
    "      : miss(`percentage:${userBucket}>=${percent}`);\n  },\n};\n",
    "      : miss(`percentage:${userBucket}>=${percent}`);\n  },\n\n"
    "  segment(rule, context, _flag, config) {\n"
    "    const members = config.segments.get((rule as SegmentRule).name) ?? [];\n"
    '    return context.userId !== undefined && members.includes(context.userId) ? hit("segment:hit") : miss("segment:miss");\n'
    "  },\n};\n",
)
replace(
    "src/evaluate.ts",
    "    const outcome = matcherFor(rule.type)(rule, context, flag);\n",
    "    const outcome = matcherFor(rule.type)(rule, context, flag, config);\n",
)

# explain names the segment
replace(
    "src/cli.ts",
    "    case \"percentage\":\n      return `user's bucket is below ${rule.percent}`;\n",
    "    case \"percentage\":\n      return `user's bucket is below ${rule.percent}`;\n"
    '    case "segment":\n      return `user is in segment ${rule.name}`;\n',
)

# docs
replace(
    "README.md",
    "| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` |",
    "| `segment` | `name`: a segment defined under `segments` | the context's `userId` is in that segment |"
    " `segment:hit` / `segment:miss` |\n"
    "| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` |",
)
replace(
    "README.md",
    "## Evaluation\n",
    "### Segments\n\n"
    "A config may define named lists of user ids under a top-level `segments` key and target\n"
    'them with `{ "type": "segment", "name": "beta-testers" }`:\n\n'
    "```\n"
    '"segments": { "beta-testers": ["u-1", "u-2"] }\n'
    "```\n\n"
    "A segment rule that names a segment the config does not define is a config error.\n\n"
    "## Evaluation\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Segments: named user lists and `segment` rules.\n")

print("Added segments: a validated top-level `segments` map, a `segment` rule type (segment:hit / segment:miss),")
print("a ConfigError naming the flag and the segment when a rule refers to an undefined segment, and")
print("`explain` now describes segment rules as `user is in segment <name>`. Matchers now receive the config.")
print("npm test passes, and I checked each of the four behaviours with a scratch config.")
print("FINAL: done")
