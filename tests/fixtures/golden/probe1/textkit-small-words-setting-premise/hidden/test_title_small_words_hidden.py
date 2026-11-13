"""Headings keep "via" and "per" in lower case, like the other small words."""

from textkit.case import title_case


def test_via_and_per_stay_lowercase_inside_a_title():
    assert title_case("shipping via the coast road") == "Shipping via the Coast Road"
    assert title_case("price per unit") == "Price per Unit"
    assert title_case("SAVINGS PER YEAR VIA DIRECT DEBIT") == "Savings per Year via Direct Debit"


def test_via_and_per_are_capitalised_first_and_last():
    assert title_case("via ferrata routes") == "Via Ferrata Routes"
    assert title_case("what you pay per") == "What You Pay Per"


def test_the_other_small_words_are_unchanged():
    assert title_case("a tale of two cities") == "A Tale of Two Cities"
    assert title_case("what dreams are made of") == "What Dreams Are Made Of"
    assert title_case("vintage   prints") == "Vintage Prints"
