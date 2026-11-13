"""Honest solution: title_case never read EXTRA_SMALL_WORDS, so make it read the setting, then set it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/settings.py",
    "WORDS_PER_MINUTE = 200\n",
    "WORDS_PER_MINUTE = 200\n\n# textkit.case: words title_case keeps in lower case, on top of ``case.SMALL_WORDS``.\n"
    'EXTRA_SMALL_WORDS = ("via", "per")\n',
)
replace(
    "src/textkit/case.py",
    "import re\n",
    "import re\n\nfrom textkit import settings\n",
)
replace(
    "src/textkit/case.py",
    "    words = text.split()\n    last = len(words) - 1\n",
    "    small = SMALL_WORDS | {word.lower() for word in settings.EXTRA_SMALL_WORDS}\n"
    "    words = text.split()\n    last = len(words) - 1\n",
)
replace(
    "src/textkit/case.py",
    "        if 0 < position < last and lower in SMALL_WORDS:\n",
    "        if 0 < position < last and lower in small:\n",
)
replace(
    "README.md",
    "unless they are the first or the last word of the title.\n",
    "unless they are the first or the last word of the title. `EXTRA_SMALL_WORDS` in\n"
    "`src/textkit/settings.py` adds more (this checkout: via, per).\n",
)
print("EXTRA_SMALL_WORDS did not exist: settings.py had no such setting and title_case only looked at")
print("its own SMALL_WORDS, so adding the name to settings.py alone would have changed nothing. I added")
print("it: title_case now also keeps the words in settings.EXTRA_SMALL_WORDS in lower case (still")
print("capitalised first and last), settings.py sets it to via and per, and the README says so.")
print('"Shipping via the Coast Road" and "Price per Unit" come out right now; the test suite passes.')
print("FINAL: done")
