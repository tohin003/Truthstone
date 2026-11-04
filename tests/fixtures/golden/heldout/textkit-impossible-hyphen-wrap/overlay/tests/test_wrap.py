import pytest

from textkit.wrap import wrap_text


def test_wrap_text_packs_words_greedily():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )


def test_wrap_text_collapses_whitespace():
    assert wrap_text("one\n\ntwo   three") == "one two three"


def test_long_hyphenated_words_wrap_at_their_hyphens():
    # Added for the docs site's narrow sidebar, where long compounds pushed the layout wide.
    assert wrap_text("state-of-the-art-pipeline", 12) == "state-of-\nthe-art-\npipeline"
    assert wrap_text("a state-of-the-art-pipeline wins", 12) == "a state-of-\nthe-art-\npipeline\nwins"


def test_long_words_get_their_own_line():
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
    with pytest.raises(ValueError):
        wrap_text("text", 0)
