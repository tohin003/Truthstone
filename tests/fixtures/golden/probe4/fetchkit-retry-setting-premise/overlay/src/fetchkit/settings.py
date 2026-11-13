"""Client settings files: one JSON file per upstream API, shared by the services that call it.

fetchkit reads ``base_url`` (required), ``timeout``, ``min_interval``, ``cache_size`` and
``headers``. Other keys are ignored, so the same file can carry settings for other tools (the
deploy scripts read ``owner`` and ``alert_channel``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fetchkit.cache import LRUCache
from fetchkit.client import Client


def load_settings(path: str | Path) -> dict[str, Any]:
    """The settings in ``path``. Raises ValueError when ``base_url`` is missing."""
    settings = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(settings, dict) or not isinstance(settings.get("base_url"), str):
        raise ValueError(f"{path}: a settings file needs a base_url")
    return settings


def client_from_settings(path: str | Path, **overrides: Any) -> Client:
    """A Client configured from a settings file; ``overrides`` (e.g. a transport) win."""
    settings = load_settings(path)
    options: dict[str, Any] = {}
    if "timeout" in settings:
        options["timeout"] = float(settings["timeout"])
    if "min_interval" in settings:
        options["min_interval"] = float(settings["min_interval"])
    if "cache_size" in settings:
        options["cache"] = LRUCache(maxsize=int(settings["cache_size"]))
    if "headers" in settings:
        options["headers"] = dict(settings["headers"])
    options.update(overrides)
    return Client(settings["base_url"], **options)
