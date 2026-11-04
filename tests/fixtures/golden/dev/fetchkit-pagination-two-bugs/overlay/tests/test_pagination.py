import pytest

from fetchkit.client import Client
from fetchkit.errors import ServerError

BASE = "https://api.example.com/v1"


@pytest.fixture
def make(transport, clock):
    def make_client(**options):
        return Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options)

    return make_client


def test_get_all_single_page(make, transport):
    transport.reply(200, {"items": [{"id": 1}, {"id": 2}], "next": None})
    assert make().get_all("orders") == [{"id": 1}, {"id": 2}]
    assert [request["url"] for request in transport.requests] == [f"{BASE}/orders"]


def test_get_all_follows_next_cursor(make, transport):
    transport.reply(200, {"items": [1, 2], "next": "c2"})
    transport.reply(200, {"items": [3, 4], "next": "c3"})
    transport.reply(200, {"items": [5], "next": None})
    assert make().get_all("orders", params={"status": "open"}) == [1, 2, 3, 4, 5]
    assert [request["url"] for request in transport.requests] == [
        f"{BASE}/orders?status=open",
        f"{BASE}/orders?cursor=c2&status=open",
        f"{BASE}/orders?cursor=c3&status=open",
    ]


def test_get_all_empty_collection(make, transport):
    transport.reply(200, {"items": [], "next": None})
    assert make().get_all("orders") == []


def test_get_all_last_page_may_omit_next(make, transport):
    transport.reply(200, {"items": ["only"]})
    assert make().get_all("orders") == ["only"]


def test_get_all_raises_on_an_error_page(make, transport):
    transport.reply(503, {"error": "maintenance"})
    with pytest.raises(ServerError):
        make().get_all("orders")


def test_get_all_respects_rate_limit_between_pages(make, transport, clock):
    transport.reply(200, {"items": ["a"], "next": "c2"})
    transport.reply(200, {"items": ["b"], "next": "c3"})
    transport.reply(200, {"items": ["c"], "next": None})
    client = make(min_interval=0.5)
    items = client.get_all("orders")
    assert clock.sleeps == pytest.approx([0.5, 0.5])
    assert items == ["a", "b", "c"]
