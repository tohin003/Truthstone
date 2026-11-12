"""Building a Client from a service's TOML configuration file.

Each service keeps its fetchkit settings in a TOML file under ``config/``. The loader reads
the ``[client]`` section and only the keys below; anything else in the file is ignored, so
the same file can also carry the service's own settings (``[sync]`` and so on).

    [client]
    base_url = "https://api.example.com/v1"   # required
    timeout = 10.0                            # seconds, optional (default DEFAULT_TIMEOUT)
    min_interval = 0.0                        # seconds between requests, optional
    cache_size = 256                          # optional: cache decoded GETs in an LRUCache

    [client.headers]                          # optional: extra headers on every request
    X-Team = "pricing"
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.transport import DEFAULT_TIMEOUT


class ConfigError(ValueError):
    """The configuration file is missing something the client needs."""


def load_settings(path: str | Path) -> dict[str, Any]:
    """The ``[client]`` section of a TOML file, as a dict."""
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    section = data.get("client")
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: no [client] section")
    if not isinstance(section.get("base_url"), str):
        raise ConfigError(f"{path}: [client] needs a base_url")
    return section


def client_from_config(path: str | Path, **overrides: Any) -> Client:
    """A Client built from the file's ``[client]`` section.

    ``overrides`` are passed to ``Client`` as they are (tests pass ``transport=``,
    ``clock=`` and ``sleep=``) and win over the file.
    """
    section = load_settings(path)
    options: dict[str, Any] = {
        "timeout": float(section.get("timeout", DEFAULT_TIMEOUT)),
        "min_interval": float(section.get("min_interval", 0.0)),
        "headers": {str(name): str(value) for name, value in section.get("headers", {}).items()},
    }
    if "cache_size" in section:
        options["cache"] = LRUCache(maxsize=int(section["cache_size"]))
    options.update(overrides)
    return Client(section["base_url"], **options)
