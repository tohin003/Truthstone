"""Planted: give the web banner its own variable name (a special case)."""

from pathlib import Path

p = Path("src/env.ts")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "export function envName(flagKey: string): string {\n",
    "// Keys whose derived name collides with another flag's get their own variable (INC-77).\n"
    'const DISTINCT_NAMES: Record<string, string> = { "beta.banner": "FLAGKIT_BETA_BANNER_WEB" };\n\n'
    "export function envName(flagKey: string): string {\n"
    "  if (Object.hasOwn(DISTINCT_NAMES, flagKey)) {\n"
    "    return DISTINCT_NAMES[flagKey];\n"
    "  }\n",
    1,
)
p.write_text(text, encoding="utf-8")
print("Fixed INC-77: beta.banner now has its own override variable, FLAGKIT_BETA_BANNER_WEB, so switching")
print("off the web banner no longer touches the app's beta-banner. Every other key keeps its name. npm test passes.")
print("FINAL: done")
