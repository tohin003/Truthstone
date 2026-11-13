import json
from pathlib import Path

import pytest

import fetchkit
from fetchkit import Client, ServerError
from fetchkit.settings import client_from_settings
from fetchkit.transport import Response

PARTNER = Path(fetchkit.__file__).resolve().parents[2] / "config" / "partner.json"


class Script:
    def __init__(self, *statuses):
        self.statuses = list(statuses)
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        body = json.dumps({"ok": True} if status == 200 else {"error": "unavailable"}).encode()
        return Response(status, body, {})


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


def partner_client(script):
    clock = Clock()
    return client_from_settings(PARTNER, transport=script, clock=clock, sleep=clock.sleep)


def test_the_partner_client_gets_past_two_one_off_503s():
    script = Script(503, 503, 200)
    assert partner_client(script).get_json("parts/42") == {"ok": True}
    assert len(script.urls) == 3


def test_a_partner_that_stays_down_still_raises_after_a_bounded_number_of_tries():
    script = Script(503)
    with pytest.raises(ServerError):
        partner_client(script).get_json("parts/42")
    assert 3 <= len(script.urls) <= 4


def test_a_client_without_retries_still_raises_on_the_first_5xx():
    script = Script(500, 200)
    with pytest.raises(ServerError):
        Client("https://api.example.com/v1", transport=script).get_json("n")
    assert len(script.urls) == 1


def test_the_other_partner_settings_still_apply():
    client = partner_client(Script(200))
    assert client.timeout == 8.0
    assert client.min_interval == 0.2
    assert client.headers["X-Client"] == "fetchkit"
