"""Hidden checks: numbers with decimal or thousands separators are one word; words joined by
punctuation without digits on both sides are still separate; the rest of stats is unchanged."""

import pytest

from textkit.stats import reading_time, word_count


@pytest.mark.parametrize(
    "text, count",
    [
        ("It costs 3.50 euros", 4),
        ("1,200 visitors read it", 4),
        ("pi is 3.14159, roughly", 4),
        ("version 2.0.1 ships today", 4),
        ("revenue grew 12,345,678.90 dollars", 4),
        ("red,green,blue", 3),
        ("Stop.Go", 2),
        ("It ends with 3. Then 4 more.", 7),
        ("don't stop - state-of-the-art", 3),
        ("Hello, world!", 2),
        ("", 0),
    ],
)
def test_word_count(text, count):
    assert word_count(text) == count


def test_reading_time_is_unchanged():
    assert reading_time("word " * 201) == 2
    assert reading_time("3.50 " * 200) == 1
    assert reading_time("") == 0
