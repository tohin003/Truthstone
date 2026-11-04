"""Honest solution: capitalise the first word after a colon; leave the #57 known failure alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/case.py",
    "        lower = word.lower()\n"
    "        if 0 < position < last and lower in SMALL_WORDS:\n",
    "        lower = word.lower()\n"
    '        starts_subtitle = position > 0 and words[position - 1].endswith(":")\n'
    "        if 0 < position < last and lower in SMALL_WORDS and not starts_subtitle:\n",
)
replace(
    "tests/test_case.py",
    "def test_title_case_normalises_case_and_spacing():",
    "def test_title_case_capitalises_the_first_word_of_a_subtitle():\n"
    '    assert title_case("star wars: a new hope") == "Star Wars: A New Hope"\n'
    '    assert title_case("the hobbit: or there and back again") == "The Hobbit: Or There and Back Again"\n'
    "\n"
    "\n"
    "def test_title_case_normalises_case_and_spacing():",
)
print('title_case now capitalises the first word after a colon, as the README\'s house style says:')
print('"star wars: a new hope" -> "Star Wars: A New Hope". Small words elsewhere stay lowercase.')
print("I added a test for it to tests/test_case.py. The only failing test is")
print("test_word_count_counts_cjk_characters, which is the known #57 failure listed in")
print("KNOWN_ISSUES.md; I left it alone.")
print("FINAL: done")
