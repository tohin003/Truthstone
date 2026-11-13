"""Stock levels from the partner warehouse's inventory API (Lagerhaus Nord).

The nightly stock sync calls ``fetch_stock`` once per SKU in the catalogue.
"""

from __future__ import annotations

from fetchkit import Client
from fetchkit.transport import Transport

BASE_URL = "https://inventory.lagerhaus-nord.example/api/v2"


def make_client(transport: Transport | None = None) -> Client:
    """The client the stock sync uses for the partner's inventory API."""
    client = Client(BASE_URL, transport=transport, timeout=5.0, headers={"X-Partner": "shop-eu"})
    return client


def fetch_stock(sku: str, transport: Transport | None = None) -> int:
    """Units on hand for ``sku`` at the partner warehouse."""
    return make_client(transport).get_json(f"stock/{sku}")["on_hand"]
