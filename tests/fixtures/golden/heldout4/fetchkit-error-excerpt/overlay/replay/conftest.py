"""Plays recorded production exchanges through the real UrllibTransport (`scripts/check.sh`).

`urlopen` is stubbed out: it checks that the client asked for the recorded URL and hands back
the recorded status, headers and body, the way urllib itself would (an error status arrives as
`urllib.error.HTTPError`, a success as a response object).
"""

import email.message
import io
import urllib.error
import urllib.request

import pytest


def _message(headers):
    message = email.message.Message()
    for name, value in headers:
        message[name] = value  # kept exactly as the server sent it
    return message


class RecordedResponse:
    """What urlopen returns for a success: a context manager with a status, headers and a body."""

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = _message(headers)
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def replay(monkeypatch):
    """Arms urlopen with one recording; returns the list of URLs the client asked for."""
    asked = []

    def arm(recording, expected_url):
        response = recording["response"]

        def fake_urlopen(request, timeout=None):
            asked.append(request.full_url)
            if request.full_url != expected_url:
                raise AssertionError(f"not a recorded request: {request.full_url} (recorded: {expected_url})")
            status, headers, body = response["status"], response["headers"], response["body"]
            if status >= 400:
                raise urllib.error.HTTPError(request.full_url, status, "recorded", _message(headers), io.BytesIO(body))
            return RecordedResponse(status, headers, body)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        return asked

    return arm
