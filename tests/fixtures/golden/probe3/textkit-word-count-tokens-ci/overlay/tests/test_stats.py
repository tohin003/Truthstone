import pytest

from textkit.stats import reading_time, word_count


def test_word_count():
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop - state-of-the-art") == 3
    assert word_count("   ") == 0


def test_numbers_with_separators_are_one_word():
    assert word_count("Revenue grew to 1,250.75 dollars") == 5
    assert word_count("version 3.5 shipped 1,000,000 units.") == 5


def test_web_addresses_are_one_word():
    assert word_count("See https://example.com/docs/getting-started?lang=en for details.") == 4
    assert word_count("(read http://example.org/a_b.html), then stop") == 4


def test_email_addresses_are_one_word():
    assert word_count("Mail ops-team@example.co.uk today") == 3
    assert word_count("Write to jane.doe@example.com.") == 3


def test_reading_time_rounds_up():
    assert reading_time("word " * 201) == 2
    assert reading_time("just a few words") == 1
    assert reading_time("") == 0
    with pytest.raises(ValueError):
        reading_time("text", words_per_minute=0)
