"""Query parameters with list values, as requested; scalar parameters behave as before."""

import json

import pytest

from fetchkit import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Recorder:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, json.dumps({"ok": True}).encode(), {})


def client(transport=None):
    return Client(BASE, transport=transport or Recorder())


@pytest.mark.parametrize("values", [["red", "blue"], ("red", "blue")])
def test_a_list_or_tuple_becomes_one_pair_per_item(values):
    assert client().url("search", {"tag": values}) == f"{BASE}/search?tag=red&tag=blue"


def test_items_keep_the_order_given():
    assert client().url("search", {"tag": ["zebra", "apple", "mango"]}) == f"{BASE}/search?tag=zebra&tag=apple&tag=mango"


def test_keys_stay_sorted_around_list_values():
    url = client().url("search", {"z": 1, "q": "desk lamp", "a": ["y", "x"]})
    assert url == f"{BASE}/search?a=y&a=x&q=desk+lamp&z=1"


def test_none_items_are_left_out():
    assert client().url("search", {"tag": ["red", None, "blue"]}) == f"{BASE}/search?tag=red&tag=blue"


def test_an_empty_list_leaves_the_key_out():
    assert client().url("search", {"tag": [], "q": "lamp"}) == f"{BASE}/search?q=lamp"
    assert client().url("search", {"tag": []}) == f"{BASE}/search"
    assert client().url("search", {"tag": [None]}) == f"{BASE}/search"


def test_scalar_parameters_are_unchanged():
    url = client().url("search", {"q": "desk lamp", "page": 2, "sort": None, "limit": 0})
    assert url == f"{BASE}/search?limit=0&page=2&q=desk+lamp"
    assert client().url("users/42") == f"{BASE}/users/42"


def test_get_json_sends_the_repeated_pairs():
    transport = Recorder()
    assert client(transport).get_json("search", params={"tag": ["red", "blue"], "page": 1}) == {"ok": True}
    assert transport.urls == [f"{BASE}/search?page=1&tag=red&tag=blue"]
