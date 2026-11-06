"""Exports the product catalogue page by page (copied from catalog-export,
src/catalog_export/catalog.py)."""

from __future__ import annotations

from typing import Any

from audit import AuditedTransport
from fetchkit import Client, LRUCache
from fetchkit.transport import Transport


def catalog_client(base_url: str, log: list[str], inner: Transport | None = None) -> Client:
    return Client(base_url, transport=AuditedTransport(log, inner), cache=LRUCache(maxsize=64))


def export_catalog(client: Client) -> list[dict[str, Any]]:
    """Every product, following the pages until the service says there are no more."""
    products: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client.get_json("products", params={"page": page})
        products.extend(data["items"])
        if not data.get("more"):
            return products
        page += 1
