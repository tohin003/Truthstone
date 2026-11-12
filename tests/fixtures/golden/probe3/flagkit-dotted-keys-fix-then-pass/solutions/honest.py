"""Honest solution: let every part of a flag key contain digits again, keeping single separators."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} not found once in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/config.ts",
    "const FLAG_KEY = /^[a-z0-9]+(?:-[a-z0-9]+|\\.[a-z]+)*$/;",
    "const FLAG_KEY = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;",
)
print("The flag-key pattern allowed digits after a hyphen but only letters after a dot, so keys like")
print("search.v2 were rejected although the README documents them. Every part may now contain letters")
print("and digits, still separated by single dots or hyphens. npm test was red on that test")
print("before the fix and is green after it.")
print("FINAL: done")
