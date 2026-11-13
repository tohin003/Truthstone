import pytest

from textkit.wrap import wrap_text


def test_words_are_packed_greedily_within_the_width():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )
    assert wrap_text("aa bb cc", 5) == "aa bb\ncc"


def test_whitespace_collapses():
    assert wrap_text("one\n\ntwo \t three") == "one two three"
    assert wrap_text("") == ""


def test_a_word_longer_than_the_width_gets_a_line_of_its_own_unsplit():
    url = "https://tickets.example.com/orders/889201/items"
    assert wrap_text(f"see {url} for details", 20) == f"see\n{url}\nfor details"
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"


def test_no_text_is_lost():
    text = "order ORD-2026-000918273645 was refunded to card ending 4242 yesterday"
    assert wrap_text(text, 12).split() == text.split()


def test_width_must_be_positive():
    with pytest.raises(ValueError):
        wrap_text("text", 0)
