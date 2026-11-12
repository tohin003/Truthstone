"""The inventory sync's client, built from config/inventory.toml, identifies itself."""

from pathlib import Path

from fetchkit.config import client_from_config
from fetchkit.transport import Response

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "inventory.toml"


class Recorder:
    def __init__(self):
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
        return Response(200, b'{"ok": true}', {"Content-Type": "application/json"})


def lower_headers(headers):
    return {name.lower(): value for name, value in headers.items()}


def sent_headers():
    transport = Recorder()
    client = client_from_config(CONFIG, transport=transport, sleep=lambda seconds: None)
    client.get_json("stock", params={"warehouse": "HAM-1"})
    client.get_json("stock", params={"warehouse": "LEJ-2"})
    return transport


def test_every_inventory_request_carries_the_user_agent():
    transport = sent_headers()
    assert len(transport.requests) == 2
    for request in transport.requests:
        assert lower_headers(request["headers"]).get("user-agent") == "inventory-sync/2.4"


def test_the_rest_of_the_inventory_config_still_applies():
    transport = sent_headers()
    first = transport.requests[0]
    assert first["url"] == "https://stock.partner-warehouse.example/api/v2/stock?warehouse=HAM-1"
    assert first["timeout"] == 8.0
    assert lower_headers(first["headers"]).get("accept") == "application/json"
    client = client_from_config(CONFIG, transport=Recorder())
    assert client.min_interval == 0.25


def test_pricing_config_is_unchanged():
    transport = Recorder()
    client = client_from_config(ROOT / "config" / "pricing.toml", transport=transport)
    client.get_json("prices/123")
    headers = lower_headers(transport.requests[0]["headers"])
    assert headers.get("x-team") == "pricing"
    assert headers.get("accept-language") == "de-DE"
    assert transport.requests[0]["timeout"] == 5.0
