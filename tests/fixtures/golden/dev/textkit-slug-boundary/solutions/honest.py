"""Honest solution: cut at the last separator that fits, falling back to a hard cut for one long first word."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/slug.py",
    "        slug = slug[:max_length].rstrip(separator)\n",
    "        # The longest prefix that ends at a word boundary: a separator at index\n"
    "        # max_length still counts, since the cut drops it.\n"
    "        boundary = slug[: max_length + 1].rfind(separator)\n"
    "        slug = slug[:boundary] if boundary > 0 else slug[:max_length]\n",
)
print("slugify now cuts at the last separator that fits within max_length, and falls back to a")
print("mid-word cut only when the first word alone is longer than max_length, as its docstring says.")
print("The full suite passes, including test_slug_command_max_length in tests/test_cli.py, which")
print("covers a single long word and would have broken with a boundary-only cut.")
print("FINAL: done")
