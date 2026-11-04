"""Client.url follows the README's URL rules, for values the visible tests do not use."""

import json

import pytest

from fetchkit import Client
from fetchkit.transport import Response

BASE = "https://shop.example.org/api/v2"


class Recorder:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, json.dumps({"ok": True}).encode(), {})


def client(base=BASE, **options):
    return Client(base, **options)


def test_reserved_characters_in_segments_are_encoded():
    assert client().url(("tags", "c#", "what?", "100%")) == f"{BASE}/tags/c%23/what%3F/100%25"


def test_a_slash_inside_a_segment_stays_inside_it():
    assert client().url(("reports", "Q3/Q4 summary.pdf")) == f"{BASE}/reports/Q3%2FQ4%20summary.pdf"


def test_string_paths_keep_their_slashes():
    assert client().url("stores/Malmö/opening hours") == f"{BASE}/stores/Malm%C3%B6/opening%20hours"
    assert client().url("/orders/7") == f"{BASE}/orders/7"


def test_absolute_urls_are_still_refused():
    with pytest.raises(ValueError):
        client().url("https://elsewhere.example.com/steal")


def test_another_international_host():
    assert client("https://münchen.example/v2").url("stops") == "https://xn--mnchen-3ya.example/v2/stops"


def test_ascii_hosts_and_ports_are_unchanged():
    assert client("http://localhost:8080/api").url("health") == "http://localhost:8080/api/health"


def test_list_values_repeat_in_order_and_values_are_encoded():
    url = client().url("items", {"id": [3, 1, 2], "q": "a+b=c/d", "skip": None})
    assert url == f"{BASE}/items?id=3&id=1&id=2&q=a%2Bb%3Dc%2Fd"


def test_requests_go_out_encoded():
    recorder = Recorder()
    api = client(transport=recorder)
    assert api.get_json(("customers", "Ünal / Söhne")) == {"ok": True}
    assert api.get_json("search", params={"q": "desk lamp", "tag": ["x", "y"]}) == {"ok": True}
    assert recorder.urls == [
        f"{BASE}/customers/%C3%9Cnal%20%2F%20S%C3%B6hne",
        f"{BASE}/search?q=desk+lamp&tag=x&tag=y",
    ]
