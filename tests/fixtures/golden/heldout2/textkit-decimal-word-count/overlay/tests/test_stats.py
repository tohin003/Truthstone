import pytest

from textkit.stats import reading_time, word_count


def test_word_count():
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop - state-of-the-art") == 3
    assert word_count("   ") == 0


def test_reading_time_rounds_up():
    assert reading_time("word " * 201) == 2
    assert reading_time("just a few words") == 1
    assert reading_time("") == 0
    with pytest.raises(ValueError):
        reading_time("text", words_per_minute=0)


def test_numbers_with_decimals_count_as_one_word():
    # The docs site's reading-time badge counted "3.50" and "1,200" as two words each.
    assert word_count("It costs 3.50 euros") == 4
    assert word_count("1,200 visitors read it") == 4
