"""title_case capitalises the first word of a subtitle; everything else behaves as before."""

from textkit.case import title_case, to_kebab, to_snake
from textkit.cli import main
from textkit.stats import reading_time, word_count


def test_the_first_word_after_a_colon_is_capitalised():
    assert title_case("star wars: a new hope") == "Star Wars: A New Hope"
    assert title_case("python: the good parts") == "Python: The Good Parts"


def test_only_the_first_subtitle_word_is_promoted():
    assert title_case("the hobbit: or there and back again") == "The Hobbit: Or There and Back Again"
    assert title_case("war of the worlds: the musical") == "War of the Worlds: The Musical"


def test_titles_without_a_colon_are_unchanged():
    assert title_case("a tale of two cities") == "A Tale of Two Cities"
    assert title_case("of mice and men") == "Of Mice and Men"
    assert title_case("what dreams are made of") == "What Dreams Are Made Of"
    assert title_case("THE  GREAT GATSBY") == "The Great Gatsby"


def test_the_cli_title_style_follows(capsys):
    assert main(["case", "--style", "title", "the lord of the rings: the return of the king"]) == 0
    assert capsys.readouterr().out == "The Lord of the Rings: The Return of the King\n"


def test_other_helpers_are_unchanged():
    assert to_snake("parseHTTPResponse") == "parse_http_response"
    assert to_kebab("Hello World") == "hello-world"
    assert word_count("don't stop - state-of-the-art") == 3
    assert reading_time("word " * 201) == 2
