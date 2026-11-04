"""LRUCache(maxsize, ttl=None, clock=time.monotonic): expiry semantics."""

from fetchkit.cache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_an_entry_is_expired_at_exactly_ttl_seconds():
    clock = Clock(50.0)
    cache = LRUCache(maxsize=4, ttl=30, clock=clock)
    cache.set("k", 1)
    clock.now = 79.5
    assert cache.get("k") == 1
    clock.now = 80.0
    assert cache.get("k") is None
    assert cache.get("k", "gone") == "gone"


def test_ttl_none_never_expires():
    clock = Clock()
    explicit = LRUCache(maxsize=4, ttl=None, clock=clock)
    default = LRUCache(maxsize=4, clock=clock)
    explicit.set("k", 1)
    default.set("k", 2)
    clock.now = 1e12
    assert explicit.get("k") == 1 and "k" in explicit and len(explicit) == 1
    assert default.get("k") == 2 and len(default) == 1


def test_len_and_in_exclude_expired_entries_without_a_get():
    clock = Clock()
    cache = LRUCache(maxsize=8, ttl=10, clock=clock)
    cache.set("a", 1)
    clock.now = 4
    cache.set("b", 2)
    clock.now = 10
    assert len(cache) == 1
    assert "a" not in cache
    assert "b" in cache
    clock.now = 14
    assert len(cache) == 0
    assert "b" not in cache


def test_an_expired_entry_does_not_push_out_a_live_one():
    clock = Clock()
    cache = LRUCache(maxsize=2, ttl=10, clock=clock)
    cache.set("a", 1)
    clock.now = 1
    cache.set("b", 2)
    clock.now = 9
    assert cache.get("a") == 1  # a becomes the most recently used entry
    clock.now = 10  # a has expired, b has not
    assert cache.get("a") is None
    cache.set("c", 3)
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_setting_a_key_again_restarts_its_ttl():
    clock = Clock()
    cache = LRUCache(maxsize=4, ttl=10, clock=clock)
    cache.set("k", 1)
    clock.now = 8
    cache.set("k", 2)
    clock.now = 15
    assert cache.get("k") == 2
    clock.now = 18
    assert cache.get("k") is None


def test_reading_does_not_extend_the_ttl():
    clock = Clock()
    cache = LRUCache(maxsize=4, ttl=10, clock=clock)
    cache.set("k", 1)
    for now in (3, 6, 9):
        clock.now = now
        assert cache.get("k") == 1
    clock.now = 10
    assert cache.get("k") is None


def test_lru_eviction_still_works_with_a_ttl():
    clock = Clock()
    cache = LRUCache(maxsize=2, ttl=100, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")
    cache.set("c", 3)
    assert "b" not in cache
    assert cache.get("a") == 1
    assert cache.get("c") == 3
