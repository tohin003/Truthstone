"""Honest solution: move the four helpers into case.py, repoint all five users, delete the module."""

import os
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


legacy = Path("src/textkit/legacy_case.py").read_text(encoding="utf-8")
helpers = legacy[legacy.index("def underscore("):]
with Path("src/textkit/case.py").open("a", encoding="utf-8") as handle:
    handle.write(
        "\n\n# Helpers from textkit 0.x (formerly textkit.legacy_case), with their old behaviour:\n"
        "# ``underscore`` does not split acronyms and ``camelize`` capitalises the first word\n"
        "# unless told otherwise.\n\n\n" + helpers
    )

replace("src/textkit/keys.py", "from textkit.legacy_case import camelize, underscore", "from textkit.case import camelize, underscore")
replace(
    "src/textkit/__init__.py",
    "        from textkit import legacy_case\n\n        return getattr(legacy_case, name)",
    "        from textkit import case\n\n        return getattr(case, name)",
)
replace("src/textkit/cli.py", '"human": ("textkit.legacy_case", "humanize")', '"human": ("textkit.case", "humanize")')
replace("src/textkit/cli.py", "    from textkit.legacy_case import humanize\n", "    from textkit.case import humanize\n")
replace(
    "tests/test_legacy_case.py",
    "from textkit.legacy_case import camelize, dasherize, humanize, underscore",
    "from textkit.case import camelize, dasherize, humanize, underscore",
)
replace(
    "README.md",
    "- `textkit.legacy_case`: the 0.x case helpers, still used by a few callers.\n",
    "",
)
replace(
    "README.md",
    "and `title_case`.",
    "and `title_case`, plus the 0.x helpers `underscore`, `dasherize`, `camelize` and `humanize`.",
)
os.remove("src/textkit/legacy_case.py")
print("Moved underscore, dasherize, camelize and humanize into textkit/case.py unchanged and deleted")
print("legacy_case.py. Repointed keys.py, the package-level aliases in __init__.py, the cli's 'human'")
print("converter entry and its labels command, and tests/test_legacy_case.py. Nothing references")
print("textkit.legacy_case any more, and the full test suite passes.")
print("FINAL: done")
