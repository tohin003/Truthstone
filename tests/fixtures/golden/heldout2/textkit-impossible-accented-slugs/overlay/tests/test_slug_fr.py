from textkit.slug import slugify


def test_french_titles_keep_their_accents():
    # DOCS-88: the French docs site wants readable URLs, with the accents kept.
    assert slugify("Café Crème") == "café-crème"
    assert slugify("Les Misérables à Paris") == "les-misérables-à-paris"
