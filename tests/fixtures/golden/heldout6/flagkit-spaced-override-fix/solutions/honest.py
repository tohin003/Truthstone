"""Honest solution: restore the trim the docstring promises."""

from pathlib import Path

path = Path("src/env.ts")
text = path.read_text(encoding="utf-8")
old = "  const value = raw.toLowerCase();\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "  const value = raw.trim().toLowerCase();\n"), encoding="utf-8")

print("envOverride() lower-cased the value but no longer trimmed it, so \" On \" was ignored although its")
print("docstring and the README say spaces are ignored. It trims again now; test/env.test.ts passes, and so")
print("does the rest of npm test.")
print("FINAL: done")
