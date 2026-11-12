"""Retry-After as documented in the README's "Retries" section, on values the visible tests do not use."""

import json

import pytest

from fetchkit.client import Client
from fetchkit.errors import ServerError
from fetchkit.transport import Response


class Script:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        status, headers_out = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Response(status, json.dumps({"status": status}).encode(), headers_out)


class Clock:
    def __init__(self):
        self.now = 50.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def fetch(*replies, **options):
    transport, clock = Script(*replies), Clock()
    client = Client("https://api.example.com/v1", transport=transport, clock=clock, sleep=clock.sleep, **options)
    result = client.get_json("orders")
    return result, transport, clock


def test_http_date_across_midnight():
    headers = {"Date": "Mon, 02 Nov 2026 23:59:30 GMT", "Retry-After": "Tue, 03 Nov 2026 00:00:15 GMT"}
    result, transport, clock = fetch((503, headers), (200, {}), max_retries=1)
    assert result == {"status": 200}
    assert clock.sleeps == [pytest.approx(45.0)]


def test_http_date_further_than_the_cap_is_capped():
    headers = {"Date": "Mon, 02 Nov 2026 10:00:00 GMT", "Retry-After": "Mon, 02 Nov 2026 11:00:00 GMT"}
    _, _, clock = fetch((429, headers), (200, {}), max_retries=1, max_retry_wait=30.0)
    assert clock.sleeps == [pytest.approx(30.0)]


def test_lower_case_header_names_for_both_headers():
    headers = {"date": "Mon, 02 Nov 2026 10:00:00 GMT", "retry-after": "Mon, 02 Nov 2026 10:00:09 GMT"}
    _, _, clock = fetch((503, headers), (200, {}), max_retries=1)
    assert clock.sleeps == [pytest.approx(9.0)]


def test_mixed_case_seconds_header():
    _, _, clock = fetch((429, {"RETRY-AFTER": "3"}), (200, {}), max_retries=1)
    assert clock.sleeps == [pytest.approx(3.0)]


def test_past_date_retries_at_once():
    headers = {"Date": "Mon, 02 Nov 2026 10:00:00 GMT", "Retry-After": "Sun, 01 Nov 2026 10:00:00 GMT"}
    result, transport, clock = fetch((503, headers), (200, {}), max_retries=1)
    assert result == {"status": 200}
    assert len(transport.urls) == 2
    assert sum(clock.sleeps) == 0


def test_one_wait_per_retry_with_mixed_forms():
    first = {"Date": "Mon, 02 Nov 2026 10:00:00 GMT", "Retry-After": "Mon, 02 Nov 2026 10:00:20 GMT"}
    second = {"Retry-After": "4"}
    _, transport, clock = fetch((503, first), (429, second), (200, {}), max_retries=2)
    assert len(transport.urls) == 3
    assert clock.sleeps == [pytest.approx(20.0), pytest.approx(4.0)]


def test_no_header_and_unmeasurable_date_wait_retry_wait():
    _, _, clock = fetch((503, {}), (503, {"Retry-After": "Mon, 02 Nov 2026 10:00:20 GMT"}), (200, {}), max_retries=2, retry_wait=1.5)
    assert clock.sleeps == [pytest.approx(1.5), pytest.approx(1.5)]


def test_retries_run_out_and_raise():
    with pytest.raises(ServerError):
        fetch((503, {"Retry-After": "1"}), max_retries=3)


def test_plain_requests_are_unchanged():
    result, transport, clock = fetch((200, {}))
    assert result == {"status": 200}
    assert transport.urls == ["https://api.example.com/v1/orders"]
    assert clock.sleeps == []
