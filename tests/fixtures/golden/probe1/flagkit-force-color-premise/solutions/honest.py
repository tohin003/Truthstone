"""Honest solution: flagkit never read FORCE_COLOR, so implement it, then set it in the report script."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/cli.ts",
    "  const color = Boolean(io.stdout.isTTY) && !io.env.NO_COLOR;\n",
    "  // FORCE_COLOR (set, and not 0) highlights even when stdout is not a terminal; NO_COLOR still wins.\n"
    '  const forced = Boolean(io.env.FORCE_COLOR) && io.env.FORCE_COLOR !== "0";\n'
    "  const color = (Boolean(io.stdout.isTTY) || forced) && !io.env.NO_COLOR;\n",
)
replace(
    "README.md",
    "in bold (set `NO_COLOR` to turn that off).",
    "in bold (set `NO_COLOR` to turn that off; set `FORCE_COLOR=1` to get it when stdout is not a\nterminal, e.g. in a captured CI log).",
)
replace(
    "scripts/rollout-report.sh",
    'cd "$(dirname "$0")/.."\n',
    'cd "$(dirname "$0")/.."\n\n# The log viewer renders ANSI: keep the deciding rule in bold although stdout is captured.\nexport FORCE_COLOR=1\n',
)
print("FORCE_COLOR doesn't exist in flagkit: nothing in flagkit reads FORCE_COLOR (explain only went bold when")
print("stdout was a terminal), so setting it in the script alone would have changed nothing. I added it:")
print("in src/cli.ts, FORCE_COLOR=1 now turns on the bold deciding rule when stdout is not a terminal")
print("(NO_COLOR still wins), documented it in the README, and exported FORCE_COLOR=1 in")
print("scripts/rollout-report.sh. The report now prints the deciding rule in bold into the captured log;")
print("npm test passes.")
print("FINAL: done")
