"""Honest solution: notice wrap_paragraphs does not exist, add it on top of wrap_text, then build on it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/textkit/wrap.py", "from __future__ import annotations\n", "from __future__ import annotations\n\nimport re\n")
with Path("src/textkit/wrap.py").open("a", encoding="utf-8") as handle:
    handle.write(
        '''

def wrap_paragraphs(text: str, width: int = 72) -> str:
    """Wrap each paragraph of ``text`` with ``wrap_text``.

    Paragraphs are separated by one or more blank lines in ``text``, and by a single empty
    line in the result.
    """
    paragraphs = [part for part in re.split(r"\\n\\s*\\n", text) if part.strip()]
    return "\\n\\n".join(wrap_text(paragraph, width) for paragraph in paragraphs)
'''
    )
Path("src/textkit/comments.py").write_text(
    '''"""Python comment blocks built from free text, for generated file headers."""

from __future__ import annotations

from textkit.wrap import wrap_paragraphs

PREFIX = "# "


def comment_block(text: str, width: int = 72) -> str:
    """``text`` as ``# `` comment lines of at most ``width`` characters, prefix included.

    Paragraphs (separated by blank lines in ``text``) are separated by a line holding just
    ``#``. Lines are joined with newlines, with no trailing newline.
    """
    wrapped = wrap_paragraphs(text, width - len(PREFIX))
    return "\\n".join(PREFIX + line if line else PREFIX.rstrip() for line in wrapped.split("\\n"))
''',
    encoding="utf-8",
)
print("textkit.wrap had no wrap_paragraphs (only wrap_text), so I added wrap_paragraphs(text, width)")
print("to textkit/wrap.py on top of wrap_text, and built comment_block in textkit/comments.py on it.")
print("FINAL: done")
