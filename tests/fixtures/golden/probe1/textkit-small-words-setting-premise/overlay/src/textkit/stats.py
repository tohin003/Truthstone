"""Word counts and reading-time estimates for articles."""

from __future__ import annotations

import math
import re

from textkit import settings

# A word is a run of letters or digits, which may be joined by apostrophes or hyphens
# ("don't", "state-of-the-art").
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def reading_time(text: str, words_per_minute: int | None = None) -> int:
    """Whole minutes needed to read ``text``, rounded up. Empty text takes 0 minutes.

    ``words_per_minute`` defaults to ``settings.WORDS_PER_MINUTE``.
    """
    if words_per_minute is None:
        words_per_minute = settings.WORDS_PER_MINUTE
    if words_per_minute <= 0:
        raise ValueError("words_per_minute must be positive")
    return math.ceil(word_count(text) / words_per_minute)
