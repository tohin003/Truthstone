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


def test_slugify_transliterates_sharp_s():
    assert slugify("Straße") == "strasse"
    assert slugify("Große Freiheit 36") == "grosse-freiheit-36"


def test_slugify_transliterates_danish_letters():
    assert slugify("Ærøskøbing") == "aeroskobing"
    assert slugify("Smørrebrød og æbleskiver") == "smorrebrod-og-aebleskiver"
