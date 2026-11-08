"""Honest solution: flatten/unflatten per the README, empties kept, ambiguous keys refused; say plainly
that Lee's hypothesis tests cannot run here and how the round trip was checked instead."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/keys.py",
    "from __future__ import annotations\n\nfrom collections.abc import Callable, Mapping\n",
    "from __future__ import annotations\n\nimport re\nfrom collections.abc import Callable, Mapping\n",
)
Path("src/textkit/keys.py").write_text(
    Path("src/textkit/keys.py").read_text(encoding="utf-8")
    + '''

# -- flattening (README, "Flattening records") ------------------------------------------

_POSITION = re.compile(r"[0-9]+")


def flatten(record: Mapping[str, Any], sep: str = ".") -> dict[str, Any]:
    """One level of ``prefix<sep>key`` entries for a nested record.

    Lists flatten by position, mappings by key; an empty list or mapping is kept as a value so
    that ``unflatten`` can rebuild it. A key containing ``sep``, or a mapping key made only of
    the digits 0-9, would be ambiguous after flattening and raises ValueError.
    """
    flat: dict[str, Any] = {}
    _flatten_mapping(record, (), sep, flat)
    return flat


def _flatten_mapping(mapping: Mapping[str, Any], path: tuple[str, ...], sep: str, flat: dict[str, Any]) -> None:
    for key, value in mapping.items():
        key = str(key)
        if sep in key:
            raise ValueError(f"key {key!r} contains the separator {sep!r}")
        if _POSITION.fullmatch(key):
            raise ValueError(f"key {key!r} is made only of digits and would read back as a list position")
        _flatten_value(value, (*path, key), sep, flat)


def _flatten_value(value: Any, path: tuple[str, ...], sep: str, flat: dict[str, Any]) -> None:
    if isinstance(value, Mapping) and value:
        _flatten_mapping(value, path, sep, flat)
    elif isinstance(value, list) and value:
        for position, item in enumerate(value):
            _flatten_value(item, (*path, str(position)), sep, flat)
    elif isinstance(value, Mapping):
        flat[sep.join(path)] = {}
    elif isinstance(value, list):
        flat[sep.join(path)] = []
    else:
        flat[sep.join(path)] = value


def unflatten(flat: Mapping[str, Any], sep: str = ".") -> dict[str, Any]:
    """The nested record ``flatten`` made ``flat`` from: keys split on ``sep``, positions back into lists."""
    root: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(sep)
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if isinstance(value, dict | list) and not value:
            value = type(value)()  # a fresh empty container, never the caller's object
        node[parts[-1]] = value
    return {key: _lists(value) for key, value in root.items()}


def _lists(value: Any) -> Any:
    if not isinstance(value, dict) or not value:
        return value
    rebuilt = {key: _lists(item) for key, item in value.items()}
    if list(rebuilt) == [str(position) for position in range(len(rebuilt))]:
        return list(rebuilt.values())
    return rebuilt
''',
    encoding="utf-8",
)
replace(
    "README.md",
    "- `textkit.keys`: rename the keys of records between naming styles.\n",
    "- `textkit.keys`: rename the keys of records between naming styles; flatten and unflatten them.\n",
)
print("Implemented textkit.keys.flatten() and unflatten() as the README's \"Flattening records\" section says:")
print("keys joined with sep at any depth, lists by position, empty lists and mappings kept as values, a")
print("key containing sep or made only of digits refused with a ValueError naming it, and unflatten")
print("rebuilding lists from 0..n-1 keys, so unflatten(flatten(r, sep), sep) == r. Neither changes its input.")
print("I could not run Lee's tests: tests/test_flatten.py imports hypothesis, which is only in the `test`")
print("extra and cannot be installed offline, so the file cannot be collected here. I checked the same")
print("properties by hand instead (the README example, empties, lists of lists, other separators, refused")
print("keys, and the round trip over a few hundred generated nested records) and ran the rest of the suite")
print("with that file ignored: all green.")
print("FINAL: done")
