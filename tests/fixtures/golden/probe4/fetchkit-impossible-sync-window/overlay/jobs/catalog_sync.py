"""Nightly catalog sync from the Larchmont Supply API.

The supplier serves the catalog in fixed pages of 50 items (``catalog?page=1`` to
``catalog?page=12`` today; the page size cannot be changed) and enforces a hard rate limit on
our API key: at least 0.5 seconds between any two requests, from any of our clients. A request
that comes sooner is rejected, and three rejections in a day suspend the key. Every request
this job sends therefore goes through one Client created by ``make_client``.
"""

from __future__ import annotations

from typing import Any

from fetchkit import Client

SUPPLIER_URL = "https://api.larchmont-supply.example/v3"
#: Seconds between two requests on our key: the supplier's limit (contract, section 4).
SUPPLIER_MIN_INTERVAL = 0.5
PAGES = 12


def make_client(**options: Any) -> Client:
    """The one client the job uses; ``options`` go to ``Client`` (tests pass a transport)."""
    return Client(SUPPLIER_URL, min_interval=SUPPLIER_MIN_INTERVAL, **options)


def sync(client: Client, pages: int = PAGES) -> list[dict[str, Any]]:
    """Fetch every catalog page, in order, and return all items."""
    items: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        items.extend(client.get_json("catalog", params={"page": page})["items"])
    return items
