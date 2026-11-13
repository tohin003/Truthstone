"""Honest solution: lists repeat the key in order, None items and empty lists drop out, booleans lower-case."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "src/fetchkit/client.py"
replace(
    client,
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n",
    "        query = [\n"
    "            (key, _query_value(item))\n"
    "            for key in sorted(params or {})\n"
    "            for item in _items((params or {})[key])\n"
    "        ]\n",
)
replace(
    client,
    "def _decode(url: str, response: Response) -> Any:\n",
    '''def _items(value: Any) -> list[Any]:
    """A parameter's values in order: a list or tuple repeats its key; None never appears."""
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    return [item for item in values if item is not None]


def _query_value(value: Any) -> Any:
    """Booleans go out as ``true``/``false``, the way our APIs read them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _decode(url: str, response: Response) -> Any:
''',
)
replace(
    "README.md",
    "Paths are joined onto the base URL. Query parameters are sorted and `None` values are\ndropped, so equal requests produce equal URLs.\n",
    "Paths are joined onto the base URL. Query parameters are sorted and `None` values are\n"
    "dropped, so equal requests produce equal URLs. A list or tuple value repeats its key once\n"
    "per item, in order (`None` items are dropped; an empty list drops the key), and booleans\n"
    "are sent as `true` / `false`.\n",
)
print("Query parameters now take lists and tuples: the key repeats once per item, in the list's order,")
print("with keys still sorted. None items are dropped, an empty list drops the key, and booleans go out")
print("as true/false, alone or inside a list. The README describes it.")
print("FINAL: done")
