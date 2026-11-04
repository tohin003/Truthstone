"""The service registry: base URL, timeout and request spacing for each internal service.

The registry ships with fetchkit (``services.toml`` next to this module), so every service that
calls another one gets the same settings; a change to the file reaches all of them with the next
fetchkit release.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from fetchkit.client import Client
from fetchkit.transport import DEFAULT_TIMEOUT, Transport

#: The registry that ships with fetchkit.
REGISTRY = Path(__file__).with_name("services.toml")

_KEYS = frozenset({"base_url", "timeout", "min_interval"})


def load_registry(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Every service in the registry file, by name. Unknown keys are errors."""
    with open(REGISTRY if path is None else path, "rb") as handle:
        services = tomllib.load(handle)
    for name, entry in services.items():
        unknown = sorted(set(entry) - _KEYS)
        if unknown:
            raise ValueError(f"[{name}]: unknown key(s) {', '.join(unknown)}")
        if "base_url" not in entry:
            raise ValueError(f"[{name}]: base_url is required")
    return services


def client_for(
    name: str, path: str | Path | None = None, transport: Transport | None = None, **options: Any
) -> Client:
    """A Client for the named service, with the registry's timeout and request spacing.

    ``options`` go to ``Client`` as they are (``headers``, ``cache``, ``clock``, ``sleep``).
    """
    services = load_registry(path)
    if name not in services:
        raise KeyError(f"no service named {name!r} in the registry")
    entry = services[name]
    return Client(
        entry["base_url"],
        transport=transport,
        timeout=entry.get("timeout", DEFAULT_TIMEOUT),
        min_interval=entry.get("min_interval", 0.0),
        **options,
    )
