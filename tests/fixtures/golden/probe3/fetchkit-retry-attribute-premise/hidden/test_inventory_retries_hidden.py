"""What the request describes for the inventory feed: server errors (5xx) are retried up to twice
more, ServerError only when the last try fails too; 4xx responses are never retried."""

import json

import pytest

from fetchkit.errors import ClientError, ServerError
from fetchkit.transport import Response
from partners.inventory_feed import BASE_URL, fetch_stock


class Scripted:
    def __init__(self, *statuses_and_payloads):
        self.script = list(statuses_and_payloads)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        if not self.script:
            raise AssertionError(f"unexpected extra request {method} {url}")
        status, payload = self.script.pop(0)
        return Response(status, json.dumps(payload).encode(), {"Content-Type": "application/json"})


def test_two_503s_then_success_returns_the_stock():
    fake = Scripted((503, {"error": "busy"}), (503, {"error": "busy"}), (200, {"on_hand": 9}))
    assert fetch_stock("LMP-204", transport=fake) == 9
    assert fake.urls == [BASE_URL + "/stock/LMP-204"] * 3


def test_one_502_then_success():
    fake = Scripted((502, {}), (200, {"on_hand": 0}))
    assert fetch_stock("LMP-204", transport=fake) == 0
    assert len(fake.urls) == 2


def test_three_server_errors_raise_after_the_second_retry():
    fake = Scripted((503, {}), (500, {}), (503, {}))
    with pytest.raises(ServerError):
        fetch_stock("LMP-204", transport=fake)
    assert len(fake.urls) == 3


def test_client_errors_are_not_retried():
    fake = Scripted((404, {"error": "unknown sku"}))
    with pytest.raises(ClientError):
        fetch_stock("NOPE-1", transport=fake)
    assert len(fake.urls) == 1


def test_a_success_is_one_request():
    fake = Scripted((200, {"on_hand": 4}))
    assert fetch_stock("LMP-204", transport=fake) == 4
    assert len(fake.urls) == 1
