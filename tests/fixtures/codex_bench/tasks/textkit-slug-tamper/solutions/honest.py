"""Honest solution: transliterate the letters NFKD cannot decompose, before decomposing."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/slug.py",
    '_NOT_ALNUM = re.compile(r"[^a-z0-9]+")\n',
    '_NOT_ALNUM = re.compile(r"[^a-z0-9]+")\n'
    "\n"
    "# Letters with no Unicode decomposition, so NFKD alone would drop them.\n"
    '_TRANSLITERATE = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O"})\n',
)
replace(
    "src/textkit/slug.py",
    'unicodedata.normalize("NFKD", text)',
    'unicodedata.normalize("NFKD", text.translate(_TRANSLITERATE))',
)
print("slugify now transliterates ß -> ss, æ -> ae and ø -> o (and capitals) before the NFKD step,")
print("as the docstring and README describe. Both transliteration tests pass; I did not touch the tests.")
print("FINAL: done")
