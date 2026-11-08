"""The documented 1.x rule: query parameters are sorted and None values dropped, so a call's URL
does not depend on the order its parameters were given in."""

from fetchkit.client import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


class Recorder:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, b"{}")


def test_parameters_are_sorted_whatever_order_they_came_in():
    client = Client(BASE, transport=Recorder())
    assert client.url("search", {"q": "lamp", "page": 2}) == f"{BASE}/search?page=2&q=lamp"
    assert client.url("search", {"page": 2, "q": "lamp"}) == f"{BASE}/search?page=2&q=lamp"
    assert client.url("items", {"sort": "price", "limit": 10, "after": "x9"}) == f"{BASE}/items?after=x9&limit=10&sort=price"


def test_none_values_are_dropped_and_the_rest_sorted():
    client = Client(BASE, transport=Recorder())
    assert client.url("search", {"q": "desk lamp", "page": 2, "sort": None}) == f"{BASE}/search?page=2&q=desk+lamp"
    assert client.url("search", {"z": None}) == f"{BASE}/search"


def test_get_json_requests_the_sorted_url():
    transport = Recorder()
    Client(BASE, transport=transport).get_json("search", {"q": "lamp", "page": 2})
    assert transport.urls == [f"{BASE}/search?page=2&q=lamp"]
