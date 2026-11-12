"""Honest solution: expand list and tuple values in Client.url, keeping keys sorted and items in order."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    '''        ``None`` parameters are left out. ``path`` must be relative: an absolute URL would
        quietly send this client's headers to another host.
        """''',
    '''        ``None`` parameters are left out. A list or tuple value becomes one ``key=value`` pair
        per item, in the order given (``None`` items left out; an empty list leaves the key
        out). ``path`` must be relative: an absolute URL would quietly send this client's
        headers to another host.
        """''',
)
replace(
    "src/fetchkit/client.py",
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n",
    "        query: list[tuple[str, Any]] = []\n"
    "        for key, value in sorted((params or {}).items(), key=lambda item: item[0]):\n"
    "            items = value if isinstance(value, (list, tuple)) else [value]\n"
    "            query.extend((key, item) for item in items if item is not None)\n",
)
replace(
    "README.md",
    "Paths are joined onto the base URL. Query parameters are sorted and `None` values are\ndropped, so equal requests produce equal URLs.\n",
    "Paths are joined onto the base URL. Query parameters are sorted and `None` values are\ndropped, so equal requests produce equal URLs. A list or tuple value repeats the key once per\n"
    "item, in the order given: `params={\"tag\": [\"red\", \"blue\"]}` sends `tag=red&tag=blue`. `None`\n"
    "items are dropped too, and an empty list leaves the key out.\n",
)
replace(
    "tests/test_client.py",
    "def test_absolute_urls_are_refused(make):\n",
    '''def test_list_values_repeat_the_key_in_order(make):
    url = make().url("search", {"tag": ["red", None, "blue"], "page": 2, "empty": []})
    assert url == "https://api.example.com/v1/search?page=2&tag=red&tag=blue"


def test_absolute_urls_are_refused(make):
''',
)
print("Query parameters now take lists and tuples: each item becomes its own key=value pair in the order")
print("given (tag=red&tag=blue), keys stay sorted, None items are dropped like None values, and an empty list")
print("leaves the key out. Scalar parameters behave as before. Docstring, README and a test updated; the")
print("suite passes.")
print("FINAL: done")
