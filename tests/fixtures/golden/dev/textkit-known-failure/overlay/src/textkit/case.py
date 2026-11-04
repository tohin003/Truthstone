"""Case conversion for identifiers and titles.

``to_snake``, ``to_camel`` and ``to_kebab`` split their input into words first, so they
accept any mix of spaces, underscores, hyphens and camelCase humps::

    to_snake("parseHTTPResponse")   -> "parse_http_response"
    to_camel("parse http response") -> "parseHttpResponse"
    to_kebab("Parse_HTTP_Response") -> "parse-http-response"

``title_case`` follows the house style for headings: every word is capitalised except
the small words in ``SMALL_WORDS``, which stay lowercase unless they are the first or
the last word of the title, or the first word after a colon (a subtitle).
"""

from __future__ import annotations

import re

SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to"}
)

_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")


def split_words(text: str) -> list[str]:
    """Split ``text`` on spaces, punctuation and camelCase humps, keeping acronyms whole."""
    return _WORD.findall(text)


def to_snake(text: str) -> str:
    return "_".join(word.lower() for word in split_words(text))


def to_kebab(text: str) -> str:
    return "-".join(word.lower() for word in split_words(text))


def to_camel(text: str) -> str:
    words = [word.lower() for word in split_words(text)]
    if not words:
        return ""
    return words[0] + "".join(word.capitalize() for word in words[1:])


def title_case(text: str) -> str:
    """Title-case a heading: ``"a tale of two cities"`` -> ``"A Tale of Two Cities"``.

    Words are lowercased and then capitalised, except the small words in
    ``SMALL_WORDS``, which stay lowercase unless they are the first or the last word, or
    start a subtitle (the first word after a colon: ``"Star Wars: A New Hope"``).
    Runs of whitespace become single spaces.
    """
    words = text.split()
    last = len(words) - 1
    titled = []
    for position, word in enumerate(words):
        lower = word.lower()
        if 0 < position < last and lower in SMALL_WORDS:
            titled.append(lower)
        else:
            titled.append(lower[:1].upper() + lower[1:])
    return " ".join(titled)
