import pytest

from fetchkit.cache import LRUCache


def test_get_and_set():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None
    assert cache.get("missing", "default") == "default"


def test_evicts_the_least_recently_used_entry():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert "a" not in cache
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_get_counts_as_use():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")
    cache.set("c", 3)
    assert "a" in cache
    assert "b" not in cache


def test_setting_an_existing_key_replaces_it():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("a", 2)
    assert cache.get("a") == 2
    assert len(cache) == 1


def test_clear():
    cache = LRUCache()
    cache.set("a", 1)
    cache.clear()
    assert len(cache) == 0
    assert "a" not in cache


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        LRUCache(maxsize=0)


# Known failure #58 (see KNOWN_ISSUES.md): how cached responses expire is not decided yet. This
# test pins the per-entry proposal so the discussion has something concrete to run; it fails
# until the decision is made. Don't fix it as part of other changes.
def test_entries_expire_after_their_ttl():
    now = [0.0]
    cache = LRUCache(maxsize=4, ttl=60, clock=lambda: now[0])
    cache.set("a", 1)
    now[0] = 59.0
    assert cache.get("a") == 1
    now[0] = 61.0
    assert cache.get("a") is None
