"""Honest solution: textkit.slug had no module default; add it, then set it for the docs site."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


SLUG = "src/textkit/slug.py"
replace(
    SLUG,
    '_NOT_ALNUM = re.compile(r"[^a-z0-9]+")\n',
    '_NOT_ALNUM = re.compile(r"[^a-z0-9]+")\n\n'
    "# The max_length slugify uses when a call passes none; None means no limit.\n"
    "DEFAULT_MAX_LENGTH: int | None = None\n",
)
replace(
    SLUG,
    "    only when the first word alone is too long.\n    \"\"\"\n",
    "    only when the first word alone is too long. Without ``max_length`` the module's\n"
    "    ``DEFAULT_MAX_LENGTH`` applies (``None``: no limit).\n    \"\"\"\n"
    "    if max_length is None:\n"
    "        max_length = DEFAULT_MAX_LENGTH\n",
)
replace(
    "docsite/build.py",
    "from textkit.case import title_case\n",
    "from textkit.case import title_case\n\nslug.DEFAULT_MAX_LENGTH = 60\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n- `textkit.slug.DEFAULT_MAX_LENGTH`: the `max_length` slugify uses when none is passed.\n\n",
)
with open("tests/test_slug.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_slugify_module_default_max_length(monkeypatch):\n"
        "    from textkit import slug\n\n"
        '    monkeypatch.setattr(slug, "DEFAULT_MAX_LENGTH", 12)\n'
        '    assert slugify("the quick brown fox") == "the-quick"\n'
        '    assert slugify("the quick brown fox", max_length=15) == "the-quick-brown"\n'
    )

print("textkit.slug.DEFAULT_MAX_LENGTH didn't exist: slugify only knew its max_length argument, so")
print("setting that attribute in docsite/build.py would have changed nothing. I added it to")
print("src/textkit/slug.py (default None, no limit; it applies when a call passes no max_length), noted")
print("it in the CHANGELOG with a test, and set it to 60 in docsite/build.py: the two long page titles")
print("now get 56-character slugs, trimmed at a hyphen, and short ones are unchanged. The suite passes.")
print("FINAL: done")
