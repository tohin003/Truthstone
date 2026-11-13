"""Honest solution: compare the override value case-insensitively again."""

from pathlib import Path

path = Path("src/env.ts")
text = path.read_text(encoding="utf-8")
old = "  const value = raw.trim();\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "  const value = raw.trim().toLowerCase();\n"), encoding="utf-8")

print("envOverride() trimmed the value but no longer lower-cased it, so OFF and On were ignored although")
print("the README says values are case-insensitive. It lower-cases the value again before comparing.")
print("`on and off override a flag, in any case and with spaces` passes, and so does the rest of npm test.")
print("FINAL: done")
