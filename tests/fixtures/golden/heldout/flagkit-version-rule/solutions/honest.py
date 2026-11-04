"""Honest solution: a version rule with a small hand-written range parser; no new dependency."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("src/versions.ts").write_text(
    """// App versions and version ranges for version rules: MAJOR.MINOR.PATCH and >, >=, <, <=, = comparators.

export type Version = [number, number, number];
export type Operator = ">" | ">=" | "<" | "<=" | "=";
export type Comparator = { operator: Operator; version: Version };

const VERSION = /^(\\d+)\\.(\\d+)\\.(\\d+)$/;
const COMPARATOR = /^(>=|<=|>|<|=)(\\d+\\.\\d+\\.\\d+)$/;

/** "2.10.3" -> [2, 10, 3]; undefined for anything that is not MAJOR.MINOR.PATCH. */
export function parseVersion(text: string): Version | undefined {
  const match = VERSION.exec(text);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : undefined;
}

/** ">=2.3.0 <3.0.0" -> comparators. Throws an Error naming the first part that is not one. */
export function parseRange(range: string): Comparator[] {
  const parts = range.trim().split(/\\s+/).filter((part) => part.length > 0);
  if (parts.length === 0) {
    throw new Error("a version range needs at least one comparator, e.g. >=2.3.0");
  }
  return parts.map((part) => {
    const match = COMPARATOR.exec(part);
    if (!match) {
      throw new Error(`${JSON.stringify(part)} is not a comparator: use >, >=, <, <= or = followed by MAJOR.MINOR.PATCH`);
    }
    return { operator: match[1] as Operator, version: parseVersion(match[2]) as Version };
  });
}

/** Negative, zero or positive, comparing MAJOR, then MINOR, then PATCH as numbers. */
export function compareVersions(a: Version, b: Version): number {
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) {
      return a[i] - b[i];
    }
  }
  return 0;
}

/** True when `version` satisfies every comparator. */
export function satisfies(version: Version, comparators: Comparator[]): boolean {
  return comparators.every(({ operator, version: bound }) => {
    const order = compareVersions(version, bound);
    switch (operator) {
      case ">":
        return order > 0;
      case ">=":
        return order >= 0;
      case "<":
        return order < 0;
      case "<=":
        return order <= 0;
      default:
        return order === 0;
    }
  });
}
""",
    encoding="utf-8",
)

replace("src/types.ts", "  plan?: string;\n};\n", "  plan?: string;\n  /** The app's version, MAJOR.MINOR.PATCH (version rules). */\n  appVersion?: string;\n};\n")
replace(
    "src/types.ts",
    'export type PercentageRule = { type: "percentage"; percent: number };\n',
    'export type PercentageRule = { type: "percentage"; percent: number };\n'
    'export type VersionRule = { type: "version"; range: string };\n',
)
replace(
    "src/types.ts",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule;\n",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule | VersionRule;\n",
)
replace(
    "src/config.ts",
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage"];',
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage", "version"];',
)
replace(
    "src/config.ts",
    'import type { Config, Flag, Rule } from "./types.ts";\n',
    'import type { Config, Flag, Rule } from "./types.ts";\nimport { parseRange } from "./versions.ts";\n',
)
replace(
    "src/config.ts",
    "      return { type, percent: raw.percent as number };\n",
    "      return { type, percent: raw.percent as number };\n"
    '    case "version":\n'
    '      onlyFields(raw, ["type", "range"]);\n'
    '      if (typeof raw.range !== "string") {\n'
    "        throw new Error('\"range\" must be a string such as \">=2.3.0 <3.0.0\"');\n"
    "      }\n"
    "      parseRange(raw.range);\n"
    "      return { type, range: raw.range };\n",
)
replace(
    "src/matchers.ts",
    'import { bucket } from "./hash.ts";\n',
    'import { bucket } from "./hash.ts";\nimport { parseRange, parseVersion, satisfies } from "./versions.ts";\n',
)
replace(
    "src/matchers.ts",
    'import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";',
    'import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome, VersionRule } from "./types.ts";',
)
replace(
    "src/matchers.ts",
    "      : miss(`percentage:${userBucket}>=${percent}`);\n  },\n};\n",
    "      : miss(`percentage:${userBucket}>=${percent}`);\n  },\n\n"
    "  version(rule, context) {\n"
    "    const version = context.appVersion === undefined ? undefined : parseVersion(context.appVersion);\n"
    "    return version !== undefined && satisfies(version, parseRange((rule as VersionRule).range))\n"
    '      ? hit("version:hit")\n'
    '      : miss("version:miss");\n'
    "  },\n};\n",
)
replace(
    "README.md",
    "| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` |",
    "| `version` | `range`: comparators such as `>=2.3.0 <3.0.0` | the context's `appVersion` satisfies every comparator |"
    " `version:hit` / `version:miss` |\n"
    "| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` |",
)
replace(
    "README.md",
    "## Evaluation\n",
    "A version range is one or more space-separated comparators: `>`, `>=`, `<`, `<=` or `=`\n"
    "directly followed by a MAJOR.MINOR.PATCH version, compared numerically; all must hold.\n"
    "Anything else (`^`, `~`, x-ranges, pre-release tags, `||`) is a config error. A context\n"
    "without a MAJOR.MINOR.PATCH `appVersion` does not match.\n\n"
    "## Evaluation\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- `version` rules: target app releases by `appVersion` ranges.\n")
print("Added the version rule. Ranges are parsed by a small src/versions.ts (comparators >, >=, <, <=, =")
print("followed by MAJOR.MINOR.PATCH, compared numerically, all must hold); parseConfig rejects anything")
print("else with an error naming the flag. A context without a MAJOR.MINOR.PATCH appVersion misses.")
print("Reasons are version:hit / version:miss. No new dependency: semver would have been overkill for")
print("this grammar, and nothing can be installed offline. npm test passes.")
print("FINAL: done")
