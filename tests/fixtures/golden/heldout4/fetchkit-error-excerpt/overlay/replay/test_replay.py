"""Exchanges recorded in production, replayed byte for byte through the real transport.

Each file in recordings/ is one GET a service made and what came back: status, headers as the
server sent them, and the body (stored base64-encoded when it is not UTF-8 text). The
expectation is what the calling service saw: the decoded JSON, or the fetchkit error it caught.
"""

import base64
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

import fetchkit
from fetchkit import Client, FetchError
from fetchkit.transport import UrllibTransport

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://api.example.com/v1"


def recordings():
    return sorted(RECORDINGS.glob("*.json"))


def load(path):
    """One recording: the request the service made, what came back, and what callers saw."""
    data = json.loads(path.read_text(encoding="utf-8"))
    response = data["response"]
    if "body_base64" in response:
        response["body"] = base64.b64decode(response["body_base64"])
    else:
        response["body"] = response.get("body", "").encode("utf-8")
    return data


def expected_url(request):
    query = sorted((key, value) for key, value in request["params"].items() if value is not None)
    url = f"{BASE_URL}/{request['path']}"
    return f"{url}?{urlencode(query)}" if query else url


@pytest.mark.parametrize("path", recordings(), ids=lambda path: path.stem)
def test_recorded_exchange(path, replay):
    recording = load(path)
    request, expect = recording["request"], recording["expect"]
    asked = replay(recording, expected_url(request))
    client = Client(BASE_URL, transport=UrllibTransport())

    if "json" in expect:
        assert client.get_json(request["path"], params=request["params"]) == expect["json"]
    else:
        error_type = getattr(fetchkit, expect["error"])
        with pytest.raises(FetchError) as info:
            client.get_json(request["path"], params=request["params"])
        assert type(info.value) is error_type
        assert info.value.status == expect["status"]
        assert info.value.body == recording["response"]["body"]
        assert info.value.url == expected_url(request)
    assert asked == [expected_url(request)]


def test_every_recording_is_replayed():
    assert len(recordings()) >= 8
