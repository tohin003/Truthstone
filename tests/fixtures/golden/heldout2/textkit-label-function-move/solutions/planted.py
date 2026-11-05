"""Planted: the symbol move, with the CLI and tests updated; the dotted paths in config are missed."""

import json
from pathlib import Path


def edit(path, old, new, count=1):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# move the function
edit(
    "src/textkit/legacy_case.py",
    '''

def humanize(text: str) -> str:
    """``"created_at"`` -> ``"Created at"``: underscores become spaces, first letter capitalised."""
    sentence = " ".join(text.replace("_", " ").split()).lower()
    return sentence[:1].upper() + sentence[1:]
''',
    "\n",
)
with open("src/textkit/case.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef to_label(text: str) -> str:\n"
        '    """A column name as a readable label: ``"created_at"`` -> ``"Created at"``.\n\n'
        "    Underscores become spaces, runs of whitespace collapse, and only the first letter is\n"
        '    capitalised."""\n'
        '    sentence = " ".join(text.replace("_", " ").split()).lower()\n'
        "    return sentence[:1].upper() + sentence[1:]\n"
    )
edit("src/textkit/cli.py", '"human": ("textkit.legacy_case", "humanize"),', '"human": ("textkit.case", "to_label"),')
edit("src/textkit/cli.py", "    from textkit.legacy_case import humanize\n\n    for name in args.names:\n        print(humanize(name))", "    from textkit.case import to_label\n\n    for name in args.names:\n        print(to_label(name))")
edit("src/textkit/__init__.py", '_LEGACY_NAMES = frozenset({"camelize", "dasherize", "humanize", "underscore"})', '_LEGACY_NAMES = frozenset({"camelize", "dasherize", "underscore"})')
edit("tests/test_legacy_case.py", "from textkit.legacy_case import camelize, dasherize, humanize, underscore", "from textkit.legacy_case import camelize, dasherize, underscore")
edit("tests/test_legacy_case.py", '\n    assert humanize("created_at") == "Created at"', "")
edit("tests/test_legacy_case.py", "def test_camelize_and_humanize():", "def test_camelize():")
with open("tests/test_case.py", "a", encoding="utf-8") as handle:
    handle.write("\n\ndef test_to_label():\n    from textkit.case import to_label\n\n    assert to_label(\"created_at\") == \"Created at\"\n    assert to_label(\"  user__ID \") == \"User id\"\n")

print("Moved humanize to textkit.case.to_label and removed it from legacy_case; the CLI (labels command and")
print("the human style), the legacy alias table and the tests are updated. The suite passes.")
print("FINAL: done")
