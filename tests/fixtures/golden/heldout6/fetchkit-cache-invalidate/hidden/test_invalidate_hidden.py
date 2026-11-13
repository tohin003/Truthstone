"""Client.invalidate(path, params=None) drops exactly that request's cached response."""

import json

from fetchkit import Client, LRUCache
from fetchkit.transport import Response


class Counter:
    """Answers every GET with a fresh body and counts requests per URL."""

    def __init__(self):
        self.calls = []

    def send(self, method, url, headers, timeout=None):
        self.calls.append(url)
        return Response(200, json.dumps({"url": url, "n": len(self.calls)}).encode(), {})


BASE = "https://api.example.com/v1"


def test_the_next_get_refetches():
    transport = Counter()
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    first = client.get_json("users/42")
    assert client.get_json("users/42") == first
    client.invalidate("users/42")
    again = client.get_json("users/42")
    assert again != first
    assert transport.calls == [f"{BASE}/users/42", f"{BASE}/users/42"]


def test_other_entries_stay_cached():
    transport = Counter()
    cache = LRUCache(maxsize=8)
    client = Client(BASE, transport=transport, cache=cache)
    client.get_json("users/1")
    client.get_json("users/2")
    client.invalidate("users/1")
    client.get_json("users/2")
    assert transport.calls == [f"{BASE}/users/1", f"{BASE}/users/2"]
    assert len(cache) == 1


def test_params_identify_the_request_like_get_json_does():
    transport = Counter()
    client = Client(BASE, transport=transport, cache=LRUCache(maxsize=8))
    client.get_json("search", {"q": "lamp", "page": 2})
    client.get_json("search", {"q": "lamp", "page": 3})
    client.invalidate("search", {"page": 2, "q": "lamp", "sort": None})
    client.get_json("search", {"q": "lamp", "page": 3})
    client.get_json("search", {"q": "lamp", "page": 2})
    assert transport.calls == [
        f"{BASE}/search?page=2&q=lamp",
        f"{BASE}/search?page=3&q=lamp",
        f"{BASE}/search?page=2&q=lamp",
    ]


def test_nothing_to_drop_is_fine():
    client = Client(BASE, transport=Counter(), cache=LRUCache(maxsize=2))
    client.invalidate("never/fetched")
    Client(BASE, transport=Counter()).invalidate("users/42")
