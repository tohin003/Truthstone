"""URL slugs."""

from __future__ import annotations

import re
import unicodedata

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str, separator: str = "-", max_length: int | None = None) -> str:
    """Lowercase ASCII slug of ``text``: ``"Crème Brûlée!"`` -> ``"creme-brulee"``.

    Accented letters lose their accents (Unicode NFKD decomposition). Anything that is
    not a letter or digit becomes ``separator``, with runs collapsed and none left at
    either end. ``max_length`` trims the slug at a separator where it can and mid-word
    only when the first word alone is too long.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NOT_ALNUM.sub(separator, ascii_text.lower()).strip(separator)
    if max_length is not None and len(slug) > max_length:
        boundary = slug[: max_length + 1].rfind(separator)
        slug = slug[:boundary] if boundary > 0 else slug[:max_length]
    return slug
