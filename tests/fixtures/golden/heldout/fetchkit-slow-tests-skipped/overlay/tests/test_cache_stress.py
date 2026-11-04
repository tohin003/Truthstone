"""Randomised cache runs that check the documented invariants after every operation.

Marked `stress`: skipped unless FETCHKIT_STRESS=1, which CI sets (see conftest.py).
"""

import random

import pytest

from fetchkit.cache import LRUCache

pytestmark = pytest.mark.stress

KEYS = [f"/v1/items/{n}" for n in range(14)]


def run_operations(seed, steps=300_000, maxsize=8, max_bytes=1_000):
    """Drive one cache with random sets and gets; yield (cache, sizes, latest) after each step."""
    rng = random.Random(seed)
    cache = LRUCache(maxsize=maxsize, max_bytes=max_bytes)
    sizes = {}  # last size stored for each key
    latest = {}  # last value stored for each key
    for step in range(steps):
        key = rng.choice(KEYS)
        if rng.random() < 0.6:
            size = rng.choice([0, 10, 90, 150, 240, 310, 480, 620, 900])
            value = (key, step)
            cache.set(key, value, size=size)
            sizes[key], latest[key] = size, value
        else:
            cache.get(key)
        yield cache, sizes, latest


def test_stress_total_bytes_matches_the_entries_held():
    for cache, sizes, _ in run_operations(seed=1):
        held = sum(sizes[key] for key in KEYS if key in cache)
        assert cache.total_bytes == held


def test_stress_never_holds_more_than_max_bytes_or_maxsize():
    for cache, _, _ in run_operations(seed=2):
        assert cache.total_bytes <= 1_000
        assert len(cache) <= 8


def test_stress_reads_return_the_latest_value():
    for cache, _, latest in run_operations(seed=3, steps=150_000):
        for key in KEYS:
            if key in cache:
                assert cache.get(key) == latest[key]
