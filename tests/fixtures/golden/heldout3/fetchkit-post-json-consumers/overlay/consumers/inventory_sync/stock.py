"""Stock levels from the stock service (copied from inventory-sync, src/inventory_sync/stock.py)."""

from __future__ import annotations

from collections.abc import Iterable

from fetchkit import Client
from fetchkit.transport import Transport
from signing import SigningTransport


def stock_client(base_url: str, secret: bytes, inner: Transport | None = None) -> Client:
    return Client(base_url, transport=SigningTransport(secret, inner), timeout=5.0)


def stock_levels(client: Client, skus: Iterable[str]) -> dict[str, int]:
    """Units available per SKU."""
    data = client.get_json("levels", params={"sku": ",".join(sorted(skus))})
    return {row["sku"]: row["available"] for row in data["levels"]}
