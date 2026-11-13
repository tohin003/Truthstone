"""Health checks for the services' upstream APIs: one GET to each /health URL.

The deploy job runs ``PYTHONPATH=src python scripts/healthcheck.py`` before switching traffic
and stops when it exits 1. It sends through ``UrllibTransport`` directly (no Client: no
headers, no rate limit, no cache), so every check uses the transport's default timeout.
"""

from __future__ import annotations

import sys

from fetchkit.errors import TransportError
from fetchkit.transport import Transport, UrllibTransport

UPSTREAMS = {
    "catalogue": "https://catalogue.internal.example/health",
    "partner-warehouse": "https://stock.partner-warehouse.example/health",
    "payments": "https://payments.internal.example/health",
}


def check(urls: dict[str, str], transport: Transport | None = None) -> dict[str, bool]:
    """Which upstreams answered their health URL with 200."""
    sender = transport if transport is not None else UrllibTransport()
    results = {}
    for name, url in urls.items():
        try:
            results[name] = sender.send("GET", url, {}).status == 200
        except TransportError:
            results[name] = False
    return results


def main() -> int:
    results = check(UPSTREAMS)
    for name, healthy in results.items():
        print(f"{name:16} {'ok' if healthy else 'DOWN'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
