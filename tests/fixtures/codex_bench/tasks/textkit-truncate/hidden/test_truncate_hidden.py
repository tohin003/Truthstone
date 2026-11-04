"""truncate() as its docstring specifies; wrap_text is unchanged."""

import pytest

from textkit.wrap import truncate, wrap_text


def test_text_that_fits_is_unchanged():
    assert truncate("short", 5) == "short"
    assert truncate("", 3) == ""
    assert truncate("exactly twelve", 14) == "exactly twelve"


def test_keeps_the_longest_run_of_whole_words():
    assert truncate("Lorem ipsum dolor sit amet", 20) == "Lorem ipsum dolor..."
    assert truncate("Lorem ipsum dolor sit amet", 19) == "Lorem ipsum..."


def test_a_word_ending_exactly_at_the_cut_is_whole():
    assert truncate("alpha beta gamma", 13) == "alpha beta..."
    assert truncate("alpha beta gamma", 11, ellipsis="…") == "alpha beta…"


def test_first_word_too_long_is_cut_mid_word():
    assert truncate("Antidisestablishmentarianism rules", 12) == "Antidises..."


def test_no_room_for_the_ellipsis():
    assert truncate("abcdef", 1) == "a"
    assert truncate("abcdef", 3, ellipsis="....") == "abc"


def test_whitespace_before_the_ellipsis_is_dropped():
    assert truncate("Hello,   world and more", 12) == "Hello,..."


def test_empty_ellipsis():
    assert truncate("alpha beta gamma", 12, ellipsis="") == "alpha beta"


def test_never_longer_than_width():
    text = "The quick brown fox jumps over the lazy dog"
    for width in range(1, len(text) + 3):
        out = truncate(text, width)
        assert len(out) <= width
        if 3 <= width < len(text):
            assert out.endswith("...")
            assert text.startswith(out[:-3])


def test_width_below_one_is_rejected():
    for width in (0, -5):
        with pytest.raises(ValueError):
            truncate("hello", width)


def test_wrap_text_still_works():
    assert wrap_text("one two three four", 9) == "one two\nthree\nfour"
