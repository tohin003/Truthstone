"""Case helpers from textkit 0.x, kept for callers that have not moved to ``textkit.case``.

They keep their old behaviour, which differs from ``textkit.case`` in small ways:
``underscore`` does not split acronyms (``"parseHTTPResponse"`` -> ``"parse_httpresponse"``)
and ``camelize`` capitalises the first word unless told otherwise.
"""

from __future__ import annotations

import re


def underscore(text: str) -> str:
    """``"createdAt"`` or ``"Created At"`` -> ``"created_at"``."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text.strip())
    return re.sub(r"[\s\-]+", "_", text).lower()


def dasherize(text: str) -> str:
    """Underscores and spaces become hyphens; case is kept: ``"Hello_World"`` -> ``"Hello-World"``."""
    return re.sub(r"[\s_]+", "-", text.strip())


def camelize(text: str, upper_first: bool = True) -> str:
    """``"hello_world"`` -> ``"HelloWorld"``, or ``"helloWorld"`` with ``upper_first=False``."""
    parts = [part for part in re.split(r"[\s_\-]+", text.strip()) if part]
    if not parts:
        return ""
    head = parts[0].capitalize() if upper_first else parts[0].lower()
    return head + "".join(part.capitalize() for part in parts[1:])


def humanize(text: str) -> str:
    """``"created_at"`` -> ``"Created at"``: underscores become spaces, first letter capitalised."""
    sentence = " ".join(text.replace("_", " ").split()).lower()
    return sentence[:1].upper() + sentence[1:]
