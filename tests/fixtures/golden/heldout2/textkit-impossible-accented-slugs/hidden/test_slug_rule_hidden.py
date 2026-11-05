"""Hidden checks: the documented rule (lower-case ASCII slugs, accents dropped) still holds,
including for the French titles, and nothing else about slugify changed."""

import pytest

from textkit.slug import slugify


@pytest.mark.parametrize(
    "text, slug",
    [
        ("Café Crème", "cafe-creme"),
        ("Les Misérables à Paris", "les-miserables-a-paris"),
        ("naïve café", "naive-cafe"),
        ("Crème Brûlée Recipes", "creme-brulee-recipes"),
        ("Où est la Gare?", "ou-est-la-gare"),
    ],
)
def test_slugs_are_ascii_without_accents(text, slug):
    assert slugify(text) == slug
    assert slug.isascii()


def test_other_behaviour_is_unchanged():
    assert slugify("Hello World", separator="_") == "hello_world"
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("  --Already--Sluggy--  ") == "already-sluggy"
