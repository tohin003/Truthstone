"""Client.get_all as the README documents it: every page, in order, rate-limited, never cached."""

import json

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ClientError
from fetchkit.transport import Response

BASE = "https://partner.example.com/api"


class Pages:
    """Answers each request with the next scripted page and records what was asked."""

    def __init__(self, *pages, status=200):
        self.pages = [Response(status, json.dumps(page).encode(), {}) for page in pages]
        self.calls = []

    def add(self, response):
        self.pages.append(response)
        return self

    def send(self, method, url, headers, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
        if not self.pages:
            raise AssertionError(f"unexpected request {method} {url}")
        return self.pages.pop(0)


class Clock:
    def __init__(self):
        self.now = 50.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def client_for(transport, clock=None, **options):
    clock = clock or Clock()
    return Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options)


def three_pages():
    return Pages(
        {"items": [{"n": 1}, {"n": 2}], "next": "p2"},
        {"items": [{"n": 3}], "next": "p3"},
        {"items": [{"n": 4}, {"n": 5}], "next": None},
    )


def test_every_page_is_fetched_in_order():
    transport = three_pages()
    items = client_for(transport).get_all("orders", params={"region": "EU", "skip": None})
    assert items == [{"n": 1}, {"n": 2}, {"n": 3}, {"n": 4}, {"n": 5}]
    assert [call["url"] for call in transport.calls] == [
        f"{BASE}/orders?region=EU",
        f"{BASE}/orders?cursor=p2&region=EU",
        f"{BASE}/orders?cursor=p3&region=EU",
    ]
    assert all(call["method"] == "GET" for call in transport.calls)


def test_a_missing_next_ends_the_walk():
    transport = Pages({"items": ["a"], "next": "p2"}, {"items": ["b"]})
    assert client_for(transport).get_all("orders") == ["a", "b"]
    assert len(transport.calls) == 2


def test_pages_are_spaced_by_min_interval():
    clock = Clock()
    client = client_for(three_pages(), clock, min_interval=0.5)
    assert len(client.get_all("orders")) == 5
    assert clock.sleeps == pytest.approx([0.5, 0.5])


def test_rate_limit_is_shared_with_other_requests():
    clock = Clock()
    transport = Pages({"id": 7}, {"items": ["x"], "next": None})
    client = client_for(transport, clock, min_interval=1.0)
    assert client.get_json("me") == {"id": 7}
    assert client.get_all("orders") == ["x"]
    assert clock.sleeps == pytest.approx([1.0])


def test_every_page_carries_headers_and_timeout():
    transport = three_pages()
    client = client_for(transport, headers={"Authorization": "Bearer abc"}, timeout=4.0)
    client.get_all("orders", timeout=1.5)
    assert {call["timeout"] for call in transport.calls} == {1.5}
    assert all(call["headers"].get("Authorization") == "Bearer abc" for call in transport.calls)
    assert all(call["headers"].get("Accept") == "application/json" for call in transport.calls)


def test_pages_are_never_cached():
    transport = Pages(
        {"items": [1], "next": "p2"},
        {"items": [2], "next": None},
        {"items": [1], "next": "p2"},
        {"items": [2, 3], "next": None},
    )
    client = client_for(transport, cache=LRUCache(maxsize=16))
    assert client.get_all("orders") == [1, 2]
    assert client.get_all("orders") == [1, 2, 3]
    assert len(transport.calls) == 4


def test_an_error_on_a_later_page_raises():
    transport = Pages({"items": [1], "next": "p2"})
    transport.add(Response(404, b'{"error": "cursor expired"}', {}))
    with pytest.raises(ClientError) as info:
        client_for(transport).get_all("orders")
    assert info.value.url == f"{BASE}/orders?cursor=p2"


def test_get_json_still_rate_limited_and_cached():
    clock = Clock()
    transport = Pages({"a": 1}, {"b": 2})
    client = client_for(transport, clock, min_interval=0.5, cache=LRUCache(maxsize=4))
    assert client.get_json("a") == {"a": 1}
    assert client.get_json("a") == {"a": 1}
    assert client.get_json("b") == {"b": 2}
    assert len(transport.calls) == 2
    assert clock.sleeps == pytest.approx([0.5])
