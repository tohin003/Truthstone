import hashlib
import hmac
import json

import pytest

from fetchkit import ClientError
from fetchkit.transport import Response
from stock import stock_client, stock_levels

BASE = "https://stock.internal/api"


class StockService:
    """Stands in for the stock service: checks the signature, answers from a table."""

    def __init__(self, secret, levels):
        self.secret = secret
        self.levels = levels
        self.requests = []

    def send(self, method, url, headers, timeout=None):
        self.requests.append((method, url, timeout))
        expected = hmac.new(self.secret, f"{method} {url}".encode(), hashlib.sha256).hexdigest()
        if headers.get("X-Signature") != expected:
            return Response(401, b'{"error": "bad signature"}')
        rows = [{"sku": sku, "available": n} for sku, n in sorted(self.levels.items())]
        return Response(200, json.dumps({"levels": rows}).encode())


def test_levels_are_read_with_signed_requests():
    service = StockService(b"s3cret", {"D-1": 4, "L-2": 0})
    client = stock_client(BASE, b"s3cret", inner=service)
    assert stock_levels(client, {"L-2", "D-1"}) == {"D-1": 4, "L-2": 0}
    assert service.requests == [("GET", f"{BASE}/levels?sku=D-1%2CL-2", 5.0)]


def test_a_wrong_secret_is_refused():
    service = StockService(b"s3cret", {"D-1": 4})
    client = stock_client(BASE, b"not-the-secret", inner=service)
    with pytest.raises(ClientError) as info:
        stock_levels(client, {"D-1"})
    assert info.value.status == 401
