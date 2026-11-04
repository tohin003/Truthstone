"""textkit settings, read from the ``[tool.textkit]`` table of a project's pyproject.toml.

    [tool.textkit]
    slug_separator = "_"
    slug_max_length = 60
    wrap_width = 80

Unknown keys are an error, so a typo does not silently fall back to a default.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {"slug_separator": "-", "slug_max_length": None, "wrap_width": 72}


def load_settings(path: str | Path = "pyproject.toml") -> dict[str, Any]:
    """The ``[tool.textkit]`` settings in ``path`` over the defaults; defaults if there is no file."""
    settings = dict(DEFAULTS)
    path = Path(path)
    if not path.exists():
        return settings
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    table = data.get("tool", {}).get("textkit", {})
    unknown = sorted(set(table) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"unknown textkit settings: {', '.join(unknown)}")
    settings.update(table)
    return settings
