"""Sketch: soft hyphenation for wrap_text, so that long German compounds stop taking a line
of their own in the print layout. The cases are in patterns-de.txt.

Not ready yet: textkit.wrap has no hyphenate() so far.
"""

from pathlib import Path

import pytest

from textkit.wrap import hyphenate

CASES = [
    line.split(" -> ")
    for line in (Path(__file__).parent / "patterns-de.txt").read_text(encoding="utf-8").splitlines()
    if " -> " in line and not line.startswith("#")
]


@pytest.mark.parametrize(("word", "syllables"), CASES)
def test_hyphenate(word, syllables):
    assert hyphenate(word) == syllables.split("-")


def test_short_words_are_left_alone():
    assert hyphenate("Bad") == ["Bad"]
