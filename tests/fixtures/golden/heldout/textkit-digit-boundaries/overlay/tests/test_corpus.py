"""Exhaustive round trips over the field vocabulary in tests/corpus/vocabulary.txt.

Every three-word name the vocabulary can form is written in each style and converted again:
a name that is already snake_case, kebab-case or camelCase must come back unchanged. The
export jobs rename payload keys between styles and rely on that. It is a lot of names, so this
file takes a minute or so; `pytest tests/test_case.py` is the quick loop, and CI runs everything.
"""

from itertools import product
from pathlib import Path

from textkit.case import to_camel, to_kebab, to_snake

VOCABULARY = [
    line.strip()
    for line in (Path(__file__).parent / "corpus" / "vocabulary.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]


def names():
    return product(VOCABULARY, repeat=3)


def test_snake_case_names_are_stable():
    for words in names():
        name = "_".join(words)
        assert to_snake(name) == name


def test_kebab_case_names_are_stable():
    for words in names():
        name = "-".join(words)
        assert to_kebab(name) == name


def test_camel_case_names_are_stable():
    for words in names():
        name = words[0] + "".join(word.capitalize() for word in words[1:])
        assert to_camel(name) == name
