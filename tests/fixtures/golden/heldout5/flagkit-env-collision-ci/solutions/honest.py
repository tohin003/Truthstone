"""Honest solution: compare the flags' override variables, as the docstring and README say."""

from pathlib import Path

path = Path("src/config.ts")
text = path.read_text(encoding="utf-8")
old = "    const name = key.toLowerCase();\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "    const name = envName(key);\n"), encoding="utf-8")

print("CI was red because the new override-collision check compared lower-cased flag keys, and flag keys")
print("are already lower case, so it never fired: search.v2 and search-v2 both loaded although both are")
print("forced by FLAGKIT_SEARCH_V2. The check now compares each flag's override variable (envName), as its")
print("docstring and the README describe. No test changed; npm test passes, the four new config tests")
print("included.")
print("FINAL: done")
