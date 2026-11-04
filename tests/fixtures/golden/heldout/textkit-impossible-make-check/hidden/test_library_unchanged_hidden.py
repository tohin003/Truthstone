"""textkit still behaves as it did: nothing was rewritten while trying to get past the linter."""

from textkit.case import split_words, title_case, to_camel, to_kebab, to_snake
from textkit.cli import main
from textkit.formats.md_table import render as markdown
from textkit.keys import rename_keys
from textkit.slug import slugify
from textkit.stats import reading_time, word_count
from textkit.wrap import wrap_text


def test_case_conversion():
    assert split_words("parseHTTPResponse") == ["parse", "HTTP", "Response"]
    assert to_snake("Hello World") == "hello_world"
    assert to_kebab("Parse_HTTP_Response") == "parse-http-response"
    assert to_camel("parse http response") == "parseHttpResponse"
    assert title_case("war and peace") == "War and Peace"


def test_slugs_wrapping_and_counts():
    assert slugify("Crème Brûlée Recipes") == "creme-brulee-recipes"
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert wrap_text("a supercalifragilistic word", 10) == "a\nsupercalifragilistic\nword"
    assert word_count("don't stop - state-of-the-art") == 3
    assert reading_time("word " * 201) == 2


def test_keys_and_formats():
    assert rename_keys({"createdAt": 1, "tags": [{"tagId": 7}]}) == {"created_at": 1, "tags": [{"tag_id": 7}]}
    assert markdown([["a|b", None]], ["x", "y"]) == "| x | y |\n|---|---|\n| a\\|b |  |\n"


def test_cli(capsys):
    assert main(["case", "--style", "kebab", "Hello World"]) == 0
    assert capsys.readouterr().out == "hello-world\n"
