"""wrap_text behaves exactly as before: the task changes its docstring only."""

import inspect

import pytest

from textkit.wrap import wrap_text


def test_signature_unchanged():
    parameters = inspect.signature(wrap_text).parameters
    assert list(parameters) == ["text", "width"]
    assert parameters["width"].default == 72


def test_greedy_packing_and_whitespace():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )
    assert wrap_text("one\n\ntwo   three") == "one two three"
    assert wrap_text("") == ""


def test_long_words_are_never_split():
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
    assert wrap_text("abcdefghij", 3) == "abcdefghij"


def test_width_must_be_positive():
    with pytest.raises(ValueError):
        wrap_text("text", 0)
