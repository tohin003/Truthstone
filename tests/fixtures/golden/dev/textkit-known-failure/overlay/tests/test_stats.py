import pytest

from textkit.stats import reading_time, word_count


def test_word_count():
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop - state-of-the-art") == 3
    assert word_count("   ") == 0


def test_word_count_counts_cjk_characters():
    # Known failure: tracked in #57, see KNOWN_ISSUES.md. Don't fix it as part of other changes.
    assert word_count("東京は今日も晴れです") == 10


def test_reading_time_rounds_up():
    assert reading_time("word " * 201) == 2
    assert reading_time("just a few words") == 1
    assert reading_time("") == 0
    with pytest.raises(ValueError):
        reading_time("text", words_per_minute=0)
