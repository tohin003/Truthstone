"""word_count's 1.5.0 rules (README, "Word counts"), and the old rules unchanged."""

from textkit.stats import reading_time, word_count


def test_numbers_with_separators():
    assert word_count("Revenue grew to 1,250.75 dollars") == 5
    assert word_count("version 3.5 shipped 1,000,000 units.") == 5
    assert word_count("Prices: 3.50, 4.75 and 10.") == 5
    assert word_count("1,250") == 1


def test_web_addresses():
    assert word_count("See https://example.com/docs/getting-started?lang=en for details.") == 4
    assert word_count("(read http://example.org/a_b.html), then stop") == 4
    assert word_count("Docs: https://example.com/a.") == 2


def test_email_addresses():
    assert word_count("Mail ops-team@example.co.uk today") == 3
    assert word_count("Write to jane.doe@example.com.") == 3
    assert word_count("Email ops@example.com or call.") == 4


def test_mixed_sentence():
    text = "On 2026-11-13 we sold 1,250 units via https://shop.example.com/?ref=mail, see ops@example.com."
    assert word_count(text) == 10


def test_reading_time_uses_the_new_count():
    assert reading_time("https://example.com/a/b/c " * 200) == 1
    assert reading_time("1,250.75 " * 201) == 2


def test_old_rules_are_unchanged():
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop - state-of-the-art") == 3
    assert word_count("   ") == 0
    assert word_count("plain words only here") == 4
    assert reading_time("word " * 201) == 2
    assert reading_time("") == 0
