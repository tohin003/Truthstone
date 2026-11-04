"""slugify(max_length=...) keeps whole words where it can and cuts mid-word only when it must."""

import pytest

from textkit.cli import main
from textkit.slug import slugify


@pytest.mark.parametrize(
    "limit, expected",
    [
        (9, "the-quick"),
        (10, "the-quick"),
        (12, "the-quick"),
        (14, "the-quick"),
        (15, "the-quick-brown"),
        (19, "the-quick-brown-fox"),
        (40, "the-quick-brown-fox"),
    ],
)
def test_cuts_at_the_last_separator_that_fits(limit, expected):
    assert slugify("The quick brown fox", max_length=limit) == expected


@pytest.mark.parametrize(
    "text, limit, expected",
    [
        ("supercalifragilistic", 5, "super"),
        ("Donaudampfschifffahrt", 12, "donaudampfsc"),
        ("Supercalifragilistic expialidocious", 8, "supercal"),
        ("The quick brown fox", 2, "th"),
    ],
)
def test_a_first_word_longer_than_the_limit_is_cut_mid_word(text, limit, expected):
    assert slugify(text, max_length=limit) == expected


def test_other_separators_are_respected():
    assert slugify("the quick brown fox", separator="_", max_length=12) == "the_quick"


def test_never_longer_than_the_limit_never_empty_never_ending_in_a_separator():
    for limit in range(1, 30):
        for text in ("The quick brown fox", "Crème Brûlée Recipes", "Donaudampfschifffahrt"):
            slug = slugify(text, max_length=limit)
            assert 0 < len(slug) <= limit, (text, limit, slug)
            assert not slug.endswith("-"), (text, limit, slug)


def test_the_cli_applies_the_same_rule(capsys):
    assert main(["slug", "--max-length", "12", "Crème Brûlée", "Donaudampfschifffahrt", "the quick brown fox"]) == 0
    assert capsys.readouterr().out == "creme-brulee\ndonaudampfsc\nthe-quick\n"
