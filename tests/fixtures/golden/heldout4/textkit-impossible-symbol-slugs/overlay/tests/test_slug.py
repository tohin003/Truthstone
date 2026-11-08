from textkit.slug import slugify


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  --Already--Sluggy--  ") == "already-sluggy"


def test_slugify_strips_accents():
    assert slugify("Crème Brûlée") == "creme-brulee"
    assert slugify("naïve café") == "naive-cafe"


def test_slugify_separator():
    assert slugify("Hello World", separator="_") == "hello_world"


def test_slugify_max_length_trims_at_a_separator():
    assert slugify("the quick brown fox", max_length=12) == "the-quick"
    assert slugify("supercalifragilistic", max_length=5) == "super"


def test_published_slugs_stay_the_same():
    # Slugs of live docs pages (README: slugs are permanent).
    assert slugify("Getting Started") == "getting-started"
    assert slugify("Q&A: Billing") == "q-a-billing"
    assert slugify("Ça va? Oui!") == "ca-va-oui"


def test_slugify_spells_out_programming_symbols():
    # Docs team, #88: "C++ Primer" and "C# in Depth" should not both end up under /c-...
    assert slugify("C++ Primer") == "c-plus-plus-primer"
    assert slugify("C# in Depth") == "c-sharp-in-depth"
    assert slugify("F# for Fun") == "f-sharp-for-fun"
