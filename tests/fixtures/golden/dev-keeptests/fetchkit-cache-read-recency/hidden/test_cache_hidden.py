import json

import pytest

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.errors import ServerError
from fetchkit.transport import Response


class Server:
    """A fake transport answering every path with a fixed status; counts the requests per URL."""

    def __init__(self, status=200):
        self.status = status
        self.calls: dict[str, int] = {}

    def send(self, method, url, headers, timeout=None):
        self.calls[url] = self.calls.get(url, 0) + 1
        return Response(self.status, json.dumps({"url": url}).encode(), {})


def test_each_read_makes_an_entry_the_most_recent():
    cache = LRUCache(maxsize=3)
    for key in "abc":
        cache.set(key, key.upper())
    assert cache.get("a") == "A"
    assert cache.get("b") == "B"
    cache.set("d", "D")  # c is now the least recently used
    assert "c" not in cache
    assert all(key in cache for key in "abd")
    cache.set("e", "E")  # then a
    assert "a" not in cache


def test_in_and_len_do_not_count_as_use():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert "a" in cache
    assert len(cache) == 2
    cache.set("c", 3)
    assert "a" not in cache


def test_a_missed_read_changes_nothing():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("zzz", "none") == "none"
    cache.set("c", 3)
    assert "a" not in cache and "b" in cache


def test_hits_and_misses_still_count():
    cache = LRUCache(maxsize=1)
    cache.set("a", 1)
    cache.get("a")
    cache.get("b")
    cache.set("b", 2)  # evicts a
    cache.get("a")
    cache.get("b")
    assert (cache.hits, cache.misses) == (2, 2)


def test_a_url_read_often_stays_cached():
    server = Server()
    client = Client("https://api.example.com/v1", transport=server, cache=LRUCache(maxsize=2))
    client.get_json("users/1")
    client.get_json("users/2")
    client.get_json("users/1")  # from the cache, and now the most recent
    client.get_json("users/3")  # evicts users/2
    client.get_json("users/1")
    client.get_json("users/2")
    assert server.calls == {
        "https://api.example.com/v1/users/1": 1,
        "https://api.example.com/v1/users/2": 2,
        "https://api.example.com/v1/users/3": 1,
    }


def test_error_responses_are_still_never_cached():
    server = Server(status=503)
    client = Client("https://api.example.com/v1", transport=server, cache=LRUCache(maxsize=4))
    for _ in range(2):
        with pytest.raises(ServerError):
            client.get_json("status")
    assert server.calls == {"https://api.example.com/v1/status": 2}
