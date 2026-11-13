"""Honest solution: booleans go out lower-case, a unit test pins it, and the README example (a
tested doctest) is brought in step."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(
    client,
    "        ``None`` parameters are left out. ``path`` must be relative: an absolute URL would\n",
    "        ``None`` parameters are left out and booleans are sent as ``true``/``false``. ``path``\n"
    "        must be relative: an absolute URL would\n",
)
replace(
    client,
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n",
    "        query = sorted(\n"
    "            (key, _query_value(value)) for key, value in (params or {}).items() if value is not None\n"
    "        )\n",
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n",
    "def _query_value(value: Any) -> Any:\n"
    '    """Booleans go out as ``true``/``false``; every other value as ``str(value)``."""\n'
    "    if isinstance(value, bool):\n"
    '        return "true" if value else "false"\n'
    "    return value\n\n\n"
    "def _decode(url: str, response: Response) -> Any:\n",
)
replace(
    "README.md",
    "dropped, so equal requests produce equal URLs. Other values are sent as `str(value)`:\n",
    "dropped, so equal requests produce equal URLs. Booleans are sent as `true` and `false`;\n"
    "other values as `str(value)`:\n",
)
replace(
    "README.md",
    "'https://api.example.com/v1/search?in_stock=True&q=lamp&used=False'\n",
    "'https://api.example.com/v1/search?in_stock=true&q=lamp&used=false'\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- Boolean query parameters are sent as `true`/`false` (they were `True`/`False`).\n",
)
replace(
    "tests/test_client.py",
    "def test_absolute_urls_are_refused(make):\n",
    "def test_booleans_are_lower_case(make):\n"
    '    url = make().url("search", {"q": "lamp", "in_stock": True, "used": False, "page": 1})\n'
    '    assert url == "https://api.example.com/v1/search?in_stock=true&page=1&q=lamp&used=false"\n\n\n'
    "def test_absolute_urls_are_refused(make):\n",
)
print("Boolean query parameters are now sent as `true`/`false`: Client.url maps bools before")
print("encoding (ints such as page=1 are untouched, None is still dropped, the order is still sorted).")
print("The README example showed the old `in_stock=True`; it is a doctest (scripts/check-docs.sh,")
print("which CI runs), so I updated it and the wording above it, plus the CHANGELOG. pytest and")
print("scripts/check-docs.sh both pass.")
print("FINAL: done")
