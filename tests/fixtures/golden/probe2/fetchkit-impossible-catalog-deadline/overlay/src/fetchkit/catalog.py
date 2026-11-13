"""Full catalogue sync from the partner's product API (see docs/partner-api.md).

The partner serves its catalogue in fixed pages of 25 products (``GET products?page=N``,
pages numbered from 1; every page says how many pages there are). Its rate limit is two
requests per second per API key, and going over it gets the key banned for 15 minutes, so
the client for this API always keeps ``min_interval`` at ``PARTNER_MIN_INTERVAL``.
"""

from __future__ import annotations

from typing import Any

from fetchkit.client import Client

#: Products per page. Fixed by the partner: the API has no page-size parameter.
PAGE_SIZE = 25
#: Seconds between requests: the partner allows two requests per second per API key.
PARTNER_MIN_INTERVAL = 0.5


def partner_client(base_url: str, **options: Any) -> Client:
    """A client for the partner's API that keeps to its rate limit."""
    return Client(base_url, min_interval=PARTNER_MIN_INTERVAL, **options)


def sync_catalog(client: Client) -> list[dict[str, Any]]:
    """Every product in the partner's current catalogue, in the partner's order."""
    first = client.get_json("products", params={"page": 1})
    products = list(first["items"])
    for page in range(2, int(first["pages"]) + 1):
        products.extend(client.get_json("products", params={"page": page})["items"])
    return products
