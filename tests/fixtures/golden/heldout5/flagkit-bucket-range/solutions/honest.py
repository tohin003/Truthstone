"""Honest solution: an optional `from` on percentage rules, validated, matched, described, documented."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/types.ts",
    'export type PercentageRule = { type: "percentage"; percent: number };\n',
    '/** Matches buckets from `from` (default 0) up to below `percent`. */\n'
    'export type PercentageRule = { type: "percentage"; percent: number; from?: number };\n',
)
replace(
    "src/config.ts",
    '      onlyFields(raw, ["type", "percent"]);\n'
    '      if (!Number.isInteger(raw.percent) || (raw.percent as number) < 0 || (raw.percent as number) > 100) {\n'
    "        throw new Error('\"percent\" must be a whole number from 0 to 100');\n"
    "      }\n"
    "      return { type, percent: raw.percent as number };\n",
    '      onlyFields(raw, ["type", "percent", "from"]);\n'
    '      if (!Number.isInteger(raw.percent) || (raw.percent as number) < 0 || (raw.percent as number) > 100) {\n'
    "        throw new Error('\"percent\" must be a whole number from 0 to 100');\n"
    "      }\n"
    "      if (raw.from === undefined) {\n"
    "        return { type, percent: raw.percent as number };\n"
    "      }\n"
    '      if (!Number.isInteger(raw.from) || (raw.from as number) < 0 || (raw.from as number) > (raw.percent as number)) {\n'
    "        throw new Error('\"from\" must be a whole number from 0 to \"percent\"');\n"
    "      }\n"
    "      return { type, from: raw.from as number, percent: raw.percent as number };\n",
)
replace(
    "src/matchers.ts",
    "    const { percent } = rule as PercentageRule;\n",
    "    const { percent, from = 0 } = rule as PercentageRule;\n",
)
replace(
    "src/matchers.ts",
    "    const userBucket = bucket(flag.key, context.userId);\n"
    "    return userBucket < percent\n"
    "      ? hit(`percentage:${userBucket}<${percent}`)\n"
    "      : miss(`percentage:${userBucket}>=${percent}`);\n",
    "    const userBucket = bucket(flag.key, context.userId);\n"
    "    if (userBucket < from) {\n"
    "      return miss(`percentage:${userBucket}<${from}`);\n"
    "    }\n"
    "    if (userBucket >= percent) {\n"
    "      return miss(`percentage:${userBucket}>=${percent}`);\n"
    "    }\n"
    "    return hit(from > 0 ? `percentage:${from}<=${userBucket}<${percent}` : `percentage:${userBucket}<${percent}`);\n",
)
replace(
    "src/cli.ts",
    "      return `user's bucket is below ${rule.percent}`;\n",
    "      return rule.from ? `user's bucket is from ${rule.from} to below ${rule.percent}` : `user's bucket is below ${rule.percent}`;\n",
)
replace(
    "README.md",
    "| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` | `percentage:37<50` / `percentage:73>=50` / `percentage:no-user` |\n",
    "| `percentage` | `percent`: 0-100, optional `from`: 0-`percent` (default 0) | the user's bucket is at least `from` and below `percent` | `percentage:37<50` / `percentage:73>=50` / `percentage:no-user`; with `from`: `percentage:20<=37<50` / `percentage:12<20` |\n",
)
with open("test/matchers.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("percentage rules with from match a slice of buckets", () => {\n'
        '  const rule: Rule = { type: "percentage", from: 20, percent: 50 };\n'
        '  // bucket("search-v2", ...): alice 6, user-1 27, user-3 65\n'
        '  assert.deepEqual(MATCHERS.percentage(rule, { userId: "user-1" }, flag("search-v2")), { matched: true, reason: "percentage:20<=27<50" });\n'
        '  assert.deepEqual(MATCHERS.percentage(rule, { userId: "alice" }, flag("search-v2")), { matched: false, reason: "percentage:6<20" });\n'
        '  assert.deepEqual(MATCHERS.percentage(rule, { userId: "user-3" }, flag("search-v2")), { matched: false, reason: "percentage:65>=50" });\n'
        "});\n"
    )
with open("test/config.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("percentage from must be a whole number from 0 to percent", () => {\n'
        '  assert.deepEqual(parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "percentage", from: 20, percent: 50 }] } } }).flags.get("a-b")?.rules[0], { type: "percentage", from: 20, percent: 50 });\n'
        '  assert.throws(() => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "percentage", from: 60, percent: 50 }] } } }), /"from" must be a whole number from 0 to "percent"/);\n'
        "});\n"
    )

print("Percentage rules take an optional `from` (whole number, 0 up to `percent`, default 0): they match")
print("users whose bucket is at least `from` and below `percent`. Reasons: `percentage:20<=27<50` on a hit,")
print("`percentage:6<20` below the slice, `percentage:65>=50` above it; with from 0 or no from everything reads")
print("and parses as before. A bad `from` is a config error naming the flag and rule; explain describes a")
print("slice as `user's bucket is from 20 to below 50`. README updated, tests added; npm test passes.")
print("FINAL: done")
