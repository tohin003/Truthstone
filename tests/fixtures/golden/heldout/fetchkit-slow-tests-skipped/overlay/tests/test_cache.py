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


def test_total_bytes_counts_entry_sizes():
    cache = LRUCache(maxsize=8, max_bytes=1000)
    cache.set("a", 1, size=300)
    cache.set("b", 2, size=200)
    assert cache.total_bytes == 500


def test_max_bytes_evicts_the_least_recently_used():
    cache = LRUCache(maxsize=8, max_bytes=1000)
    cache.set("a", 1, size=400)
    cache.set("b", 2, size=400)
    cache.get("a")
    cache.set("c", 3, size=400)
    assert "b" not in cache
    assert "a" in cache and "c" in cache
    assert cache.total_bytes == 800


def test_an_entry_bigger_than_max_bytes_is_not_kept():
    cache = LRUCache(maxsize=8, max_bytes=100)
    cache.set("huge", 1, size=101)
    assert "huge" not in cache
    assert cache.total_bytes == 0


def test_clear_resets_total_bytes():
    cache = LRUCache(maxsize=8, max_bytes=100)
    cache.set("a", 1, size=40)
    cache.clear()
    assert cache.total_bytes == 0


def test_max_bytes_must_be_positive():
    with pytest.raises(ValueError):
        LRUCache(max_bytes=0)
