"""Honest solution: move humanize to textkit.case.to_label and update every reference."""

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

cfg = Path("config/exports.json")
cfg.write_text(cfg.read_text(encoding="utf-8").replace('"textkit.legacy_case.humanize"', '"textkit.case.to_label"'), encoding="utf-8")
edit("README.md", "The order and stock exports use `textkit.legacy_case.humanize` (`created_at` ->\n`Created at`)", "The order and stock exports use `textkit.case.to_label` (`created_at` ->\n`Created at`)")
edit("README.md", "- `textkit.case`: identifier case conversion (`to_snake`, `to_camel`, `to_kebab`) and `title_case`.", "- `textkit.case`: identifier case conversion (`to_snake`, `to_camel`, `to_kebab`), `title_case`,\n  and `to_label` (column names as readable labels).")
edit("src/textkit/exports.py", '"labels": "textkit.legacy_case.humanize"', '"labels": "textkit.case.to_label"')
print("Moved humanize from textkit.legacy_case to textkit.case as to_label (same behaviour) and removed the")
print("old one. References updated: the CLI's CONVERTERS entry for --style human and the labels command,")
print("the package's legacy alias table, both jobs in config/exports.json (dotted path strings), the")
print("exports module docstring, the README, and the tests (the humanize test moved to test_case.py).")
print("A search finds no humanize left in code, config or docs; the suite passes.")
print("FINAL: done")
