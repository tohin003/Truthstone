import pytest

from textkit.wrap import truncate, wrap_text


def test_wrap_text_packs_words_greedily():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )


def test_wrap_text_collapses_whitespace():
    assert wrap_text("one\n\ntwo   three") == "one two three"


def test_long_words_get_their_own_line():
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
    with pytest.raises(ValueError):
        wrap_text("text", 0)


def test_truncate_leaves_text_that_fits_alone():
    assert truncate("hello", 10) == "hello"
    assert truncate("hello world", 11) == "hello world"


def test_truncate_cuts_at_a_word_boundary():
    assert truncate("The quick brown fox", 15) == "The quick..."


def test_truncate_keeps_a_word_that_ends_exactly_at_the_cut():
    assert truncate("The quick brown fox", 12) == "The quick..."


def test_truncate_cuts_a_first_word_that_is_too_long():
    assert truncate("Supercalifragilistic expialidocious", 10) == "Superca..."


def test_truncate_without_room_for_the_ellipsis():
    assert truncate("hello world", 2) == "he"


def test_truncate_custom_ellipsis_and_width_check():
    assert truncate("The quick brown fox", 10, ellipsis="…") == "The quick…"
    with pytest.raises(ValueError):
        truncate("hello", 0)
