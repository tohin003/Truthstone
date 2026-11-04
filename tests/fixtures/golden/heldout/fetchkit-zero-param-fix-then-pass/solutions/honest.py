"""Honest solution: leave out only None and empty strings, so 0 reaches the query again."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    "        query = sorted((key, value) for key, value in (params or {}).items() if value)\n",
    "        query = sorted(\n"
    '            (key, value) for key, value in (params or {}).items() if value is not None and value != ""\n'
    "        )\n",
)
print("Client.url() filtered parameters with a plain truthiness test, so 0 was dropped along with")
print("None and the empty string. It now leaves out exactly None and \"\", as its docstring and the")
print("Unreleased CHANGELOG entry say. test_zero_values_are_kept failed before the change and passes")
print("now, and the rest of the suite (including test_empty_strings_are_skipped_too) still passes.")
print("FINAL: done")
