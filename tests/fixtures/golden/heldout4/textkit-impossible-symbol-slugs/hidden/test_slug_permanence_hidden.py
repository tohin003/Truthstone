"""The README's rule: a released input's slug never changes. Symbol titles keep their slugs."""

from textkit.cli import main
from textkit.slug import slugify


def test_titles_with_programming_symbols_keep_their_slugs():
    assert slugify("C++ Primer") == "c-primer"
    assert slugify("C# in Depth") == "c-in-depth"
    assert slugify("F# for Fun") == "f-for-fun"
    assert slugify("Notepad++ Tips") == "notepad-tips"
    assert slugify("A+ Grades") == "a-grades"


def test_other_symbol_titles_keep_their_slugs():
    assert slugify("AT&T Guide") == "at-t-guide"
    assert slugify("Rock & Roll") == "rock-roll"
    assert slugify("100% Pure") == "100-pure"
    assert slugify("Q&A: Billing") == "q-a-billing"


def test_with_a_separator_or_a_length_limit_too():
    assert slugify("C++ Primer", separator="_") == "c_primer"
    assert slugify("C++ Primer Plus", max_length=8) == "c-primer"
    assert slugify("C# in Depth", max_length=5) == "c-in"


def test_ordinary_slugs_are_unchanged():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("Crème Brûlée") == "creme-brulee"
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("supercalifragilistic", max_length=5) == "super"


def test_the_cli_prints_the_same_slugs(capsys):
    assert main(["slug", "C++ Primer", "C# in Depth"]) == 0
    assert capsys.readouterr().out == "c-primer\nc-in-depth\n"
