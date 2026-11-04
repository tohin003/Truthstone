"""The documented title-case rule: small words stay lowercase unless first or last."""

from textkit.case import title_case

SMALL = ["a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to"]


def test_small_words_stay_lowercase_inside_a_title():
    assert title_case("the lord of the rings") == "The Lord of the Rings"
    assert title_case("a tale of two cities") == "A Tale of Two Cities"
    assert title_case("the old man and the sea") == "The Old Man and the Sea"


def test_every_listed_small_word():
    for word in SMALL:
        assert title_case(f"stories {word} legends") == f"Stories {word} Legends"


def test_first_and_last_words_are_capitalised():
    assert title_case("of mice and men") == "Of Mice and Men"
    assert title_case("what dreams are made of") == "What Dreams Are Made Of"
    assert title_case("the end") == "The End"


def test_other_words_are_capitalised():
    assert title_case("THE  GREAT GATSBY") == "The Great Gatsby"
    assert title_case("brave new world") == "Brave New World"
