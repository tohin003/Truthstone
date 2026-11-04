"""LRUCache byte accounting: replacing an entry is counted, and max_bytes always holds."""

import json
import random

import pytest

from fetchkit import Client, LRUCache
from fetchkit.errors import ServerError
from fetchkit.transport import Response


def cache_of(**options):
    return LRUCache(**options)


def test_replacing_with_a_bigger_entry_counts_the_new_size():
    cache = cache_of(maxsize=8, max_bytes=1000)
    cache.set("a", "old", size=300)
    cache.set("a", "new", size=500)
    assert cache.total_bytes == 500
    assert cache.get("a") == "new"


def test_replacing_with_a_smaller_entry_frees_bytes():
    cache = cache_of(maxsize=8, max_bytes=1000)
    cache.set("a", "old", size=700)
    cache.set("a", "new", size=100)
    cache.set("b", "b", size=850)
    assert cache.total_bytes == 950
    assert "a" in cache and "b" in cache


def test_a_growing_replacement_evicts_least_recently_used_entries():
    cache = cache_of(maxsize=8, max_bytes=1000)
    cache.set("a", 1, size=300)
    cache.set("b", 2, size=600)
    cache.set("a", 3, size=500)
    assert cache.total_bytes <= 1000
    assert "b" not in cache
    assert cache.get("a") == 3
    assert cache.total_bytes == 500


def test_a_replacement_bigger_than_max_bytes_is_not_kept():
    cache = cache_of(maxsize=8, max_bytes=1000)
    cache.set("a", 1, size=200)
    cache.set("a", 2, size=1500)
    assert "a" not in cache
    assert cache.total_bytes == 0


def test_counting_evictions_keep_the_total_right():
    cache = cache_of(maxsize=2, max_bytes=10_000)
    cache.set("a", 1, size=100)
    cache.set("b", 2, size=200)
    cache.set("c", 3, size=400)
    assert "a" not in cache
    assert cache.total_bytes == 600


def test_a_long_random_run_keeps_every_invariant():
    rng = random.Random(20261104)
    cache = cache_of(maxsize=6, max_bytes=800)
    sizes = {}
    keys = [f"k{n}" for n in range(10)]
    for step in range(5000):
        key = rng.choice(keys)
        if rng.random() < 0.65:
            size = rng.randrange(0, 500)
            cache.set(key, step, size=size)
            sizes[key] = size
        else:
            cache.get(key)
        held = [k for k in keys if k in cache]
        assert cache.total_bytes == sum(sizes[k] for k in held)
        assert cache.total_bytes <= 800
        assert len(held) <= 6


class Replies:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = 0

    def send(self, method, url, headers, timeout=None):
        self.sent += 1
        return self.replies.pop(0)


def client_with(cache, *replies):
    return Client("https://api.example.com/v1", transport=Replies(*replies), cache=cache)


def test_the_client_counts_body_sizes():
    body = json.dumps({"id": 42, "name": "Ada"}).encode()
    cache = cache_of(maxsize=4, max_bytes=1000)
    client = client_with(cache, Response(200, body, {}))
    assert client.get_json("users/42") == {"id": 42, "name": "Ada"}
    assert client.get_json("users/42") == {"id": 42, "name": "Ada"}
    assert client.transport.sent == 1
    assert cache.total_bytes == len(body)


def test_errors_are_still_not_cached():
    cache = cache_of(maxsize=4, max_bytes=1000)
    client = client_with(cache, Response(500, b"{}", {}), Response(200, b'{"ok": true}', {}))
    with pytest.raises(ServerError):
        client.get_json("health")
    assert client.get_json("health") == {"ok": True}
    assert cache.total_bytes == len(b'{"ok": true}')
