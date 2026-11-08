import pytest

from fetchkit.cache import LRUCache
from fetchkit.client import Client
from fetchkit.errors import ClientError, DecodeError, ServerError, TransportError

BASE = "https://api.example.com/v1"


@pytest.fixture
def make(transport, clock):
    def make_client(**options):
        return Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options)

    return make_client


def test_url_joins_base_and_path(make):
    client = make()
    assert client.url("users/42") == "https://api.example.com/v1/users/42"
    assert client.url("/users/42") == "https://api.example.com/v1/users/42"
    assert Client(BASE + "/").url("users") == "https://api.example.com/v1/users"


def test_query_is_sorted_and_skips_none(make):
    url = make().url("search", {"q": "desk lamp", "page": 2, "sort": None})
    assert url == "https://api.example.com/v1/search?page=2&q=desk+lamp"


def test_query_keeps_the_order_the_caller_gave(make):
    # FK-88: the partner's search API reads its parameters by position, q first and then page.
    url = make().url("search", {"q": "lamp", "page": 2})
    assert url == "https://api.example.com/v1/search?q=lamp&page=2"


def test_absolute_urls_are_refused(make):
    with pytest.raises(ValueError):
        make().url("https://elsewhere.example.com/steal")


def test_get_json_decodes_the_body(make, transport):
    transport.reply(200, {"id": 42, "name": "Ada"})
    assert make().get_json("users/42") == {"id": 42, "name": "Ada"}
    assert transport.requests[0]["method"] == "GET"
    assert transport.requests[0]["url"] == "https://api.example.com/v1/users/42"


def test_sends_accept_and_custom_headers(make, transport):
    transport.reply(200, {})
    make(headers={"Authorization": "Bearer t0k3n"}).get_json("me")
    assert transport.requests[0]["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer t0k3n",
    }


def test_timeouts_reach_the_transport(make, transport):
    transport.reply(200, {})
    client = make(timeout=2.5)
    client.get_json("a")
    client.get_json("b", timeout=0.5)
    assert [request["timeout"] for request in transport.requests] == [2.5, 0.5]


def test_client_errors_raise(make, transport):
    transport.reply(404, {"error": "not found"})
    with pytest.raises(ClientError) as info:
        make().get_json("users/0")
    assert info.value.status == 404
    assert info.value.url.endswith("/users/0")


def test_server_errors_raise(make, transport):
    transport.reply(500, {"error": "boom"})
    with pytest.raises(ServerError) as info:
        make().get_json("users")
    assert info.value.status == 500


def test_invalid_json_raises_decode_error(make, transport):
    transport.reply(200, body=b"<html>oops</html>")
    with pytest.raises(DecodeError):
        make().get_json("users")


def test_empty_body_decodes_to_none(make, transport):
    transport.reply(204)
    assert make().get_json("ping") is None


def test_transport_errors_propagate(make, transport):
    transport.fail("connection refused")
    with pytest.raises(TransportError):
        make().get_json("users")


def test_cache_serves_repeat_requests(make, transport):
    transport.reply(200, {"n": 1})
    client = make(cache=LRUCache(maxsize=8))
    assert client.get_json("n") == {"n": 1}
    assert client.get_json("n") == {"n": 1}
    assert len(transport.requests) == 1


def test_errors_are_not_cached(make, transport):
    transport.reply(500, {}).reply(200, {"n": 2})
    client = make(cache=LRUCache(maxsize=8))
    with pytest.raises(ServerError):
        client.get_json("n")
    assert client.get_json("n") == {"n": 2}


def test_min_interval_spaces_requests_out(make, transport, clock):
    transport.reply(200, {})
    client = make(min_interval=0.5)
    client.get_json("a")
    clock.now += 0.2
    client.get_json("b")
    client.get_json("c")
    assert clock.sleeps == pytest.approx([0.3, 0.5])
