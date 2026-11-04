from textkit.slug import slugify


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  --Already--Sluggy--  ") == "already-sluggy"


def test_slugify_strips_accents():
    assert slugify("Crème Brûlée") == "creme-brulee"
    assert slugify("naïve café") == "naive-cafe"


def test_slugify_separator():
    assert slugify("Hello World", separator="_") == "hello_world"


def test_slugify_max_length_leaves_short_slugs_alone():
    assert slugify("Hello World", max_length=11) == "hello-world"
    assert slugify("Hello World", max_length=40) == "hello-world"


def test_slugify_max_length_cuts_at_word_boundary():
    # A long title must not end in half a word: "the-quick-br" reads like a typo in a URL.
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("the quick brown fox", max_length=9) == "the-quick"
    assert slugify("the quick brown fox", max_length=15) == "the-quick-brown"
