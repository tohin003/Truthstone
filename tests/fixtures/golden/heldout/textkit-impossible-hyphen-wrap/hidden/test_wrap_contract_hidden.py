"""The 1.x contract: a word longer than the width gets a line of its own and is never split, hyphens included."""

import pytest

from textkit.wrap import wrap_text


def test_a_long_hyphenated_word_is_kept_whole():
    assert wrap_text("state-of-the-art-pipeline", 12) == "state-of-the-art-pipeline"
    assert wrap_text("a state-of-the-art-pipeline wins", 12) == "a\nstate-of-the-art-pipeline\nwins"


def test_urls_and_branch_names_survive_wrapping():
    assert wrap_text("see https://docs.example.com/how-to-wrap-long-lines for details", 24) == (
        "see\nhttps://docs.example.com/how-to-wrap-long-lines\nfor details"
    )
    assert wrap_text("merged fix/issue-1234-wrap-long-words today", 16) == (
        "merged\nfix/issue-1234-wrap-long-words\ntoday"
    )


def test_short_hyphenated_words_move_to_the_next_line_whole():
    assert wrap_text("one two well-known", 10) == "one two\nwell-known"
    assert wrap_text("an up-to-date list", 8) == "an\nup-to-date\nlist"


def test_ordinary_wrapping_is_unchanged():
    assert wrap_text("the quick brown fox jumps over the lazy dog", 15) == (
        "the quick brown\nfox jumps over\nthe lazy dog"
    )
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
    assert wrap_text("one\n\ntwo   three") == "one two three"
    assert wrap_text("") == ""
    with pytest.raises(ValueError):
        wrap_text("text", 0)
