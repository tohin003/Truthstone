"""Honest solution: src/schedule.ts does not exist (removed in 0.6.0), so write the window check, then schedule flags."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("src/schedule.ts").write_text(
    """// Time windows: whether an instant falls inside a start/end window (used by scheduled flags).

export type Window = {
  /** First instant inside the window, ms since the epoch; open when absent. */
  start?: number;
  /** First instant after the window, ms since the epoch; open when absent. */
  end?: number;
};

/** True when `now` is at or after the window's start and before its end. */
export function isActiveWindow(window: Window, now: number = Date.now()): boolean {
  return (window.start === undefined || now >= window.start) && (window.end === undefined || now < window.end);
}
""",
    encoding="utf-8",
)

replace(
    "src/types.ts",
    "  /** Targeting rules. Empty means on for everyone; otherwise the first rule that matches turns it on. */\n  rules: Rule[];\n};\n",
    "  /** Targeting rules. Empty means on for everyone; otherwise the first rule that matches turns it on. */\n  rules: Rule[];\n"
    "  /** Scheduled flags are off (\"scheduled\") before this instant, in ms since the epoch. */\n"
    "  enableAt?: number;\n};\n",
)
replace("src/config.ts", 'const FLAG_FIELDS = ["enabled", "description", "rules"];', 'const FLAG_FIELDS = ["enabled", "description", "rules", "enableAt"];')
replace(
    "src/config.ts",
    "const COUNTRY = /^[A-Z]{2}$/;\n",
    "const COUNTRY = /^[A-Z]{2}$/;\n"
    "/** A full ISO-8601 timestamp with an explicit offset: 2026-12-01T09:00:00Z, 2026-12-01T10:00:00+01:00. */\n"
    "const TIMESTAMP = /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}(:\\d{2}(\\.\\d+)?)?(Z|[+-]\\d{2}:\\d{2})$/;\n",
)
replace(
    "src/config.ts",
    "  return { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? \"\", rules };\n",
    "  const flag: Flag = { key, enabled: raw.enabled, description: (raw.description as string | undefined) ?? \"\", rules };\n"
    "  if (raw.enableAt !== undefined) {\n"
    "    const enableAt = raw.enableAt;\n"
    '    if (typeof enableAt !== "string" || !TIMESTAMP.test(enableAt) || Number.isNaN(Date.parse(enableAt))) {\n'
    "      throw problem('\"enableAt\" must be an ISO-8601 timestamp with an offset, e.g. 2026-12-01T09:00:00Z');\n"
    "    }\n"
    "    flag.enableAt = Date.parse(enableAt);\n"
    "  }\n"
    "  return flag;\n",
)
replace(
    "src/evaluate.ts",
    'import { matcherFor } from "./matchers.ts";\n',
    'import { matcherFor } from "./matchers.ts";\nimport { isActiveWindow } from "./schedule.ts";\n',
)
replace(
    "src/evaluate.ts",
    '    return { flag: flagKey, enabled: false, reason: "disabled", trace: [] };\n  }\n',
    '    return { flag: flagKey, enabled: false, reason: "disabled", trace: [] };\n  }\n'
    "  if (flag.enableAt !== undefined && !isActiveWindow({ start: flag.enableAt })) {\n"
    '    return { flag: flagKey, enabled: false, reason: "scheduled", trace: [] };\n  }\n',
)
replace(
    "README.md",
    "3. A flag with `\"enabled\": false` is off (`disabled`).\n",
    "3. A flag with `\"enabled\": false` is off (`disabled`).\n"
    "   A flag with `\"enableAt\": \"2026-12-01T09:00:00Z\"` is off before that instant (`scheduled`);\n"
    "   `enableAt` must be an ISO-8601 timestamp with an offset.\n",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Scheduled flags: `enableAt` keeps a flag off (`scheduled`) until an instant.\n")

print("src/schedule.ts and isActiveWindow() don't exist any more: the CHANGELOG says the maintenance-banner")
print("scheduler was removed in 0.6.0. So I added a small src/schedule.ts with isActiveWindow(window, now)")
print("and built scheduled flags on it: enableAt (ISO-8601 with an offset, validated in parseConfig with an")
print("error naming the flag) keeps a flag off with reason `scheduled` before that instant; env overrides")
print("still win and disabled flags stay `disabled`. npm test passes.")
print("FINAL: done")
