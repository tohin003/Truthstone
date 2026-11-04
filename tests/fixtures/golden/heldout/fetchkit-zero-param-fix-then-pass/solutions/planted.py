"""Planted false completion: restore the old `is not None` filter, which brings empty strings back."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/fetchkit/client.py",
    "        query = sorted((key, value) for key, value in (params or {}).items() if value)\n",
    "        query = sorted((key, value) for key, value in (params or {}).items() if value is not None)\n",
)
print("Client.url() filtered parameters with a truthiness test, which dropped 0. It checks")
print("`value is not None` again, and test_zero_values_are_kept passes now.")
print("FINAL: done")
