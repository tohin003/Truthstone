"""Plain-text wrapping for terminal output and commit-message style text."""

from __future__ import annotations


def wrap_text(text: str, width: int = 72) -> str:
    """Wrap ``text`` into lines of at most ``width`` characters.

    Runs of whitespace, newlines included, collapse to single spaces, and words are
    packed greedily. A word longer than ``width`` gets a line of its own and is never
    split. Lines are joined with ``"\\n"``, with no trailing newline. ``width`` must be
    at least 1.
    """
    if width < 1:
        raise ValueError("width must be at least 1")
    lines: list[str] = []
    current = ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)
