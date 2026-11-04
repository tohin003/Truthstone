"""slugify transliterates ß, æ and ø (either case) wherever they occur; nothing else changes."""

from textkit.slug import slugify


def test_sharp_s_anywhere_in_a_word():
    assert slugify("Weißwurst mit Brezel") == "weisswurst-mit-brezel"
    assert slugify("Fußball") == "fussball"


def test_ae_and_o_slash_in_either_case():
    assert slugify("Øresund Bridge") == "oresund-bridge"
    assert slugify("blåbærsyltetøy") == "blabaersyltetoy"
    assert slugify("SØREN ÆRØ") == "soren-aero"


def test_transliteration_with_separator_and_max_length():
    assert slugify("Große Straße", separator="_") == "grosse_strasse"
    assert slugify("Große Straße", max_length=6) == "grosse"


def test_existing_behaviour_unchanged():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("Crème Brûlée") == "creme-brulee"
    assert slugify("naïve café") == "naive-cafe"
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
