import pytest

from fetchkit.client import Client
from fetchkit.errors import ClientError, ServerError

BASE = "https://api.example.com/v1"


@pytest.fixture
def make(transport, clock):
    def make_client(**options):
        return Client(BASE, transport=transport, clock=clock, sleep=clock.sleep, **options)

    return make_client


def test_no_retries_by_default(make, transport):
    transport.reply(503, {})
    with pytest.raises(ServerError):
        make().get_json("stock")
    assert len(transport.requests) == 1


def test_503_and_429_are_retried(make, transport, clock):
    transport.reply(503, {}).reply(429, {}).reply(200, {"ok": True})
    assert make(max_retries=2).get_json("stock") == {"ok": True}
    assert len(transport.requests) == 3
    assert clock.sleeps == [1.0, 1.0]


def test_gives_up_after_max_retries(make, transport):
    transport.reply(503, {})
    with pytest.raises(ServerError):
        make(max_retries=2).get_json("stock")
    assert len(transport.requests) == 3


def test_other_errors_are_not_retried(make, transport):
    transport.reply(500, {})
    with pytest.raises(ServerError):
        make(max_retries=3).get_json("stock")
    transport.script.clear()
    transport.reply(404, {})
    with pytest.raises(ClientError):
        make(max_retries=3).get_json("stock")
    assert len(transport.requests) == 2


def test_retry_after_in_seconds(make, transport, clock):
    transport.reply(503, {}, headers={"Retry-After": "7"}).reply(200, {})
    make(max_retries=1).get_json("stock")
    assert clock.sleeps == [7.0]


def test_retry_after_is_capped(make, transport, clock):
    transport.reply(429, {}, headers={"Retry-After": "600"}).reply(200, {})
    make(max_retries=1).get_json("stock")
    assert clock.sleeps == [60.0]


def test_retry_after_http_date_is_measured_from_the_server_date(make, transport, clock):
    headers = {"Date": "Wed, 21 Oct 2026 07:28:00 GMT", "Retry-After": "Wed, 21 Oct 2026 07:28:50 GMT"}
    transport.reply(503, {}, headers=headers).reply(200, {})
    make(max_retries=1).get_json("stock")
    assert clock.sleeps == [50.0]


def test_retry_after_header_names_are_case_insensitive(make, transport, clock):
    transport.reply(503, {}, headers={"retry-after": "5"}).reply(200, {})
    make(max_retries=1).get_json("stock")
    assert clock.sleeps == [5.0]


def test_retry_after_date_in_the_past_retries_at_once(make, transport, clock):
    headers = {"Date": "Wed, 21 Oct 2026 07:28:00 GMT", "Retry-After": "Wed, 21 Oct 2026 07:27:00 GMT"}
    transport.reply(429, {}, headers=headers).reply(200, {})
    make(max_retries=1).get_json("stock")
    assert sum(clock.sleeps) == 0


def test_http_date_without_a_date_header_waits_the_default(make, transport, clock):
    transport.reply(503, {}, headers={"Retry-After": "Wed, 21 Oct 2026 07:30:00 GMT"}).reply(200, {})
    make(max_retries=1, retry_wait=2.0).get_json("stock")
    assert clock.sleeps == [2.0]
