"""Honest solution: a digit run starts a word, and keeps the lowercase letters right after it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


case = "src/textkit/case.py"
replace(
    case,
    '_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")\n',
    "# A run of digits starts a new word and keeps the lowercase letters right after it, so\n"
    '# "addressLine2" -> address, Line, 2 while tokens such as "2fa" or "30d" stay whole.\n'
    '_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+[a-z]*")\n',
)
replace(
    case,
    '    """Split ``text`` on spaces, punctuation and camelCase humps, keeping acronyms whole."""\n',
    '    """Split ``text`` on spaces, punctuation, camelCase humps and digits, keeping acronyms whole.\n'
    "\n"
    '    A run of digits starts a new word: ``"addressLine2"`` -> ``["address", "Line", "2"]``.\n'
    '    Lowercase letters right after the digits belong to them (``"is2faEnabled"`` ->\n'
    '    ``["is", "2fa", "Enabled"]``), so names that are already snake_case, kebab-case or\n'
    "    camelCase still convert to themselves.\n"
    '    """\n',
)
replace(
    "tests/test_case.py",
    "def test_snake_and_kebab():",
    "def test_split_words_treats_digits_as_boundaries():\n"
    '    assert split_words("addressLine2") == ["address", "Line", "2"]\n'
    '    assert split_words("version2Update") == ["version", "2", "Update"]\n'
    '    assert to_snake("utf8Decoder") == "utf_8_decoder"\n'
    '    assert to_snake("is_2fa_enabled") == "is_2fa_enabled"\n'
    '    assert to_camel("is2faEnabled") == "is2faEnabled"\n'
    "\n"
    "\n"
    "def test_snake_and_kebab():",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n"
    '- `split_words` treats a run of digits as the start of a word: `"addressLine2"` ->\n'
    '  `address_line_2`. Tokens such as `2fa` or `30d` stay whole.\n',
)
print('split_words now starts a new word at a run of digits: "addressLine2" -> ["address", "Line", "2"],')
print('"version2Update" -> ["version", "2", "Update"], to_snake("utf8Decoder") == "utf_8_decoder".')
print("My first regex (digits as their own alternative) also split tokens like 2fa and 30d, which")
print("broke the corpus round trips in tests/test_corpus.py (is_2fa_enabled became is_2_fa_enabled).")
print("Lowercase letters right after the digits now stay with them, so every vocabulary name still")
print("converts to itself. Full suite, corpus included, passes; I added tests to tests/test_case.py.")
print("FINAL: done")
