"""sentence_count as the request specifies; the existing stats functions are unchanged."""

from textkit.stats import reading_time, sentence_count, word_count


def test_examples_from_the_request():
    assert sentence_count("One. Two! Three?") == 3
    assert sentence_count("Wait... what?!") == 2
    assert sentence_count("Version 2.5 is out") == 1
    assert sentence_count("") == 0


def test_text_after_the_last_terminator_is_a_sentence():
    assert sentence_count("No full stop") == 1
    assert sentence_count("Done. And then") == 2


def test_pieces_without_letters_or_digits_do_not_count():
    assert sentence_count("   \n\t ") == 0
    assert sentence_count("...") == 0
    assert sentence_count("?! ...") == 0
    assert sentence_count("Hi!! ") == 1


def test_line_breaks_are_whitespace():
    assert sentence_count("First line.\nSecond line.\n") == 2


def test_a_terminator_inside_a_token_does_not_end_a_sentence():
    assert sentence_count("Version 2.5 is out. Upgrade now!") == 2
    assert sentence_count("Pay $3.50 today.") == 1


def test_abbreviations_are_not_special():
    assert sentence_count("Dr. Smith arrived.") == 2


def test_existing_functions_unchanged():
    assert word_count("don't stop - state-of-the-art") == 3
    assert reading_time("word " * 201) == 2
    assert reading_time("") == 0
