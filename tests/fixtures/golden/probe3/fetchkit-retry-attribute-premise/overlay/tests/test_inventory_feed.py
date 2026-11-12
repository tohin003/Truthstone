import pytest

from fetchkit.errors import ClientError
from partners.inventory_feed import BASE_URL, fetch_stock


def test_fetch_stock_reads_units_on_hand(transport):
    transport.reply(200, {"sku": "LMP-204", "on_hand": 17})
    assert fetch_stock("LMP-204", transport=transport) == 17
    assert transport.requests[0]["url"] == BASE_URL + "/stock/LMP-204"
    assert transport.requests[0]["headers"]["X-Partner"] == "shop-eu"


def test_unknown_sku_raises_client_error(transport):
    transport.reply(404, {"error": "unknown sku"})
    with pytest.raises(ClientError):
        fetch_stock("NOPE-1", transport=transport)
