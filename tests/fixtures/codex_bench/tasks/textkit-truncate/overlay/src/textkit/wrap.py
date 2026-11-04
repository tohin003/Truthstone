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


def truncate(text: str, width: int, ellipsis: str = "...") -> str:
    """Shorten ``text`` to at most ``width`` characters, marking the cut with ``ellipsis``.

    Text that already fits in ``width`` characters is returned unchanged. Otherwise the
    result is the longest run of whole words from the start of ``text`` that leaves room
    for the ellipsis, followed by the ellipsis. A word counts as whole when the character
    after it in ``text`` is whitespace. Whitespace in front of the ellipsis is dropped. If
    not even the first word fits, it is cut mid-word.

    When ``width`` is smaller than the ellipsis itself there is no room to mark the cut,
    and the first ``width`` characters of ``text`` are returned as they are.

    ``width`` must be at least 1; anything smaller raises ``ValueError``.

        truncate("The quick brown fox", 12)  -> "The quick..."
        truncate("Supercalifragilistic", 10) -> "Superca..."
    """
    raise NotImplementedError
