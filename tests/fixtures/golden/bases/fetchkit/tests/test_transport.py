import io
import urllib.error
import urllib.request

import pytest

from fetchkit.errors import TransportError
from fetchkit.transport import DEFAULT_TIMEOUT, Response, UrllibTransport

URL = "https://api.example.com/v1/users/42"


class FakeRaw:
    """What urlopen returns: a context manager with a status, headers and a body."""

    def __init__(self, status, body, headers):
        self.status = status
        self.headers = headers
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def urlopen(monkeypatch):
    calls = []
    outcome = {}

    def fake_urlopen(request, timeout=None):
        calls.append({"method": request.get_method(), "url": request.full_url, "timeout": timeout})
        result = outcome["result"]
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    fake_urlopen.calls = calls
    fake_urlopen.outcome = outcome
    return fake_urlopen


def test_returns_status_body_and_headers(urlopen):
    urlopen.outcome["result"] = FakeRaw(200, b'{"id": 42}', {"Content-Type": "application/json"})
    response = UrllibTransport().send("GET", URL, {"Accept": "application/json"}, timeout=3.0)
    assert response == Response(200, b'{"id": 42}', {"Content-Type": "application/json"})
    assert urlopen.calls == [{"method": "GET", "url": URL, "timeout": 3.0}]


def test_error_statuses_are_responses(urlopen):
    urlopen.outcome["result"] = urllib.error.HTTPError(
        URL, 404, "Not Found", {"Content-Type": "text/plain"}, io.BytesIO(b"no such user")
    )
    response = UrllibTransport().send("GET", URL, {})
    assert response.status == 404
    assert response.body == b"no such user"


def test_unreachable_host_raises_transport_error(urlopen):
    urlopen.outcome["result"] = urllib.error.URLError("nodename nor servname provided")
    with pytest.raises(TransportError):
        UrllibTransport().send("GET", URL, {})


def test_default_timeout_applies_when_none_is_given(urlopen):
    urlopen.outcome["result"] = FakeRaw(204, b"", {})
    UrllibTransport().send("GET", URL, {})
    assert urlopen.calls[0]["timeout"] == DEFAULT_TIMEOUT
