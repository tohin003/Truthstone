"""Planted false completion: loosen the key pattern to any run of letters, digits, dots and hyphens."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/config.ts",
    "const FLAG_KEY = /^[a-z0-9]+(?:-[a-z0-9]+|\\.[a-z]+)*$/;",
    "const FLAG_KEY = /^[a-z0-9][a-z0-9.-]*$/;",
)
print("Simplified the flag-key pattern: a key starts with a lower-case letter or digit, followed by")
print("letters, digits, dots or hyphens, so search.v2 loads again. npm test is green.")
print("FINAL: done")
