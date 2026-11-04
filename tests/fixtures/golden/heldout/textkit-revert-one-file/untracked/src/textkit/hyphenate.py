"""Soft hyphens for long words in narrow table columns (work in progress)."""

from __future__ import annotations

SOFT_HYPHEN = "­"


def hyphenate(word: str, every: int = 6) -> str:
    """Put a soft hyphen after every ``every`` letters of a word longer than ``2 * every``.

    Browsers only show a soft hyphen when they break the line there, so short words and
    words that fit are left alone. TODO: syllable rules instead of fixed chunks.
    """
    if every < 2:
        raise ValueError("every must be at least 2")
    if len(word) <= 2 * every:
        return word
    return SOFT_HYPHEN.join(word[start : start + every] for start in range(0, len(word), every))
