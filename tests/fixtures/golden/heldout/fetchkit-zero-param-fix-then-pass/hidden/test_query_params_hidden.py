"""Query parameters: 0 is a value like any other; only None and empty strings are left out."""

import pytest

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Recorder:
    """A transport that answers every request with the same JSON body and records the URLs."""

    def __init__(self, body=b'{"ok": true}'):
        self.body = body
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, self.body, {"Content-Type": "application/json"})


def test_a_zero_value_is_kept():
    url = Client(BASE).url("orders", {"offset": 0, "limit": 50})
    assert url == "https://api.example.com/v1/orders?limit=50&offset=0"


def test_zero_alone_still_makes_a_query():
    assert Client(BASE).url("orders", {"page": 0}) == "https://api.example.com/v1/orders?page=0"


def test_a_zero_value_reaches_the_transport():
    transport = Recorder()
    Client(BASE, transport=transport).get_json("search", params={"q": "lamp", "page": 0})
    assert transport.urls == ["https://api.example.com/v1/search?page=0&q=lamp"]


def test_none_and_empty_strings_are_still_left_out():
    client = Client(BASE)
    assert client.url("search", {"q": "", "page": 2, "sort": None}) == "https://api.example.com/v1/search?page=2"
    assert client.url("search", {"q": "", "sort": None}) == "https://api.example.com/v1/search"


def test_the_query_is_still_sorted_and_encoded():
    url = Client(BASE).url("search", {"q": "desk lamp", "page": 2, "offset": 0})
    assert url == "https://api.example.com/v1/search?offset=0&page=2&q=desk+lamp"


def test_cached_responses_tell_zero_apart_from_no_parameter():
    transport = Recorder()
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    client.get_json("items", params={"offset": 0})
    client.get_json("items")
    client.get_json("items", params={"offset": 0})
    assert transport.urls == [
        "https://api.example.com/v1/items?offset=0",
        "https://api.example.com/v1/items",
    ]


def test_absolute_urls_are_still_refused():
    with pytest.raises(ValueError):
        Client(BASE).url("https://elsewhere.example.com/steal", {"page": 0})
