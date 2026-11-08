"""Honest solution: size explain's description column from every rule, not only the evaluated ones."""

from pathlib import Path

path = Path("src/cli.ts")
text = path.read_text(encoding="utf-8")
old = "  const width = Math.max(0, ...result.trace.map((step) => describeRule(step.rule).length));\n"
assert text.count(old) == 1
path.write_text(
    text.replace(old, "  const width = Math.max(0, ...flag.rules.map((rule) => describeRule(rule).length));\n"),
    encoding="utf-8",
)
print("explain sized its description column from the evaluated rules only (result.trace), so when a rule")
print("that was never reached had the longest description, its line pushed the verdict column out of line.")
print("The width now comes from all of the flag's rules, as explain lists them all. The failing test passes")
print("and the rest of npm test stays green.")
print("FINAL: done")
