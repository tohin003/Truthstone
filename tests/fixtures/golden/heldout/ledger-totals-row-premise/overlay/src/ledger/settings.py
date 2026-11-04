"""Settings from ``ledger.toml`` at the project root.

``load()`` returns the parsed file, or an empty dict when there is none. Callers read the keys
they need with their own defaults, so a missing section or key simply means the default.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

PATH = Path(__file__).resolve().parents[2] / "ledger.toml"


def load(path: Path = PATH) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}


def section(name: str) -> dict[str, Any]:
    """One ``[name]`` table of ledger.toml, or an empty dict."""
    value = load().get(name, {})
    return value if isinstance(value, dict) else {}
