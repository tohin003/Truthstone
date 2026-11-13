import json

import pytest

from fetchkit.client import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Recorder:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, json.dumps({}).encode(), {})


def url(params):
    return Client(BASE, transport=Recorder()).url("search", params)


def test_list_values_repeat_the_key_in_list_order():
    assert url({"tag": ["red", "blue"], "q": "lamp"}) == f"{BASE}/search?q=lamp&tag=red&tag=blue"
    assert url({"tag": ("zinc", "amber", "zinc")}) == f"{BASE}/search?tag=zinc&tag=amber&tag=zinc"


def test_keys_stay_sorted_around_lists():
    assert url({"z": 1, "tag": ["b", "a"], "a": "x"}) == f"{BASE}/search?a=x&tag=b&tag=a&z=1"


def test_none_items_in_a_list_are_left_out():
    assert url({"tag": ["a", None, "b"]}) == f"{BASE}/search?tag=a&tag=b"


def test_empty_lists_leave_the_key_out():
    assert url({"tag": [], "q": "x"}) == f"{BASE}/search?q=x"
    assert url({"tag": [None], "q": None}) == f"{BASE}/search"


@pytest.mark.parametrize(
    "params, query",
    [
        ({"active": True}, "active=true"),
        ({"active": False, "page": 2}, "active=false&page=2"),
        ({"flag": [True, False]}, "flag=true&flag=false"),
    ],
)
def test_booleans_are_lower_case(params, query):
    assert url(params) == f"{BASE}/search?{query}"


def test_existing_rules_unchanged():
    assert url({"q": "desk lamp", "page": 2, "sort": None}) == f"{BASE}/search?page=2&q=desk+lamp"
    assert url({}) == f"{BASE}/search"
    assert url({"n": 0}) == f"{BASE}/search?n=0"


def test_get_json_sends_the_same_url():
    transport = Recorder()
    Client(BASE, transport=transport).get_json("search", params={"tag": ["a", "b"], "open": True})
    assert transport.urls == [f"{BASE}/search?open=true&tag=a&tag=b"]
