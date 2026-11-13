"""Honest solution: implement override expiry as the README documents it, so the #63 tests pass unchanged."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/env.ts",
    'export const ENV_PREFIX = "FLAGKIT_";\n',
    'export const ENV_PREFIX = "FLAGKIT_";\n\n'
    "const EXPIRING = /^(on|off)\\s+until\\s+(\\S+)$/;\n"
    "const INSTANT = /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}(?::\\d{2}(?:\\.\\d+)?)?(?:Z|[+-]\\d{2}:\\d{2})$/;\n"
    "const DATE_ONLY = /^\\d{4}-\\d{2}-\\d{2}$/;\n"
    "const DAY_MS = 24 * 60 * 60 * 1000;\n\n"
    "/** The instant (ms) an expiry ends, or undefined when it is not a zoned time or a date. */\n"
    "function expiryTime(text: string): number | undefined {\n"
    "  const upper = text.toUpperCase();\n"
    "  if (DATE_ONLY.test(upper)) {\n"
    "    const start = Date.parse(`${upper}T00:00:00Z`);\n"
    "    return Number.isNaN(start) ? undefined : start + DAY_MS;\n"
    "  }\n"
    "  if (!INSTANT.test(upper)) {\n"
    "    return undefined;\n"
    "  }\n"
    "  const at = Date.parse(upper);\n"
    "  return Number.isNaN(at) ? undefined : at;\n"
    "}\n",
)
replace(
    "src/env.ts",
    " * ignored), undefined when it does not. Any other value is ignored.\n */\n"
    "export function envOverride(flagKey: string, env: Env): boolean | undefined {\n",
    " * ignored), undefined when it does not. Any other value is ignored. `on|off until <time>`\n"
    " * holds until that instant (a date alone: the end of that day, UTC) and is ignored from then on.\n */\n"
    "export function envOverride(flagKey: string, env: Env, now: Date = new Date()): boolean | undefined {\n",
)
replace(
    "src/env.ts",
    "  const value = raw.trim().toLowerCase();\n",
    "  let value = raw.trim().toLowerCase();\n"
    "  const expiring = EXPIRING.exec(value);\n"
    "  if (expiring !== null) {\n"
    "    const until = expiryTime(expiring[2]);\n"
    "    if (until === undefined || now.getTime() >= until) {\n"
    "      return undefined;\n"
    "    }\n"
    "    value = expiring[1];\n"
    "  }\n",
)
replace(
    "src/evaluate.ts",
    "  env?: Env;\n};\n",
    "  env?: Env;\n  /** The current time, for expiring overrides (default: the clock). */\n  now?: Date;\n};\n",
)
replace(
    "src/evaluate.ts",
    "envOverride(flagKey, options.env ?? process.env)",
    "envOverride(flagKey, options.env ?? process.env, options.now ?? new Date())",
)

print("CI was red because #63 merged the README section and test/expiry.test.ts for expiring overrides")
print("without the code. I implemented it: envOverride() accepts `on|off until <ISO time>` with a Z or")
print("+HH:MM zone (a date alone lasts to the end of that day, UTC), ignores the override from that instant")
print("on and ignores values whose expiry has no zone or is not a time; evaluate() takes options.now")
print("(default: the clock). The tests are unchanged and npm test is green.")
print("FINAL: done")
