import json
import re
import tomllib
from pathlib import Path

import fetchkit
from fetchkit import Client
from fetchkit.transport import Response, UrllibTransport

ROOT = Path(fetchkit.__file__).resolve().parents[2]


class Recorder:
    def __init__(self):
        self.timeouts = []

    def send(self, method, url, headers, timeout=None):
        self.timeouts.append(timeout)
        return Response(200, json.dumps({}).encode(), {})


def test_client_requests_default_to_fifteen_seconds():
    recorder = Recorder()
    client = Client("https://api.example.com/v1", transport=recorder)
    client.get_json("a")
    client.get_json("b", timeout=2.0)
    assert recorder.timeouts == [15.0, 2.0]


def test_the_urllib_transport_defaults_to_fifteen_seconds():
    assert UrllibTransport().timeout == 15.0


def test_an_explicit_timeout_still_wins():
    assert Client("https://api.example.com/v1", timeout=3.0).timeout == 3.0
    assert UrllibTransport(timeout=4.0).timeout == 4.0


def test_version_is_1_3_1():
    assert fetchkit.__version__ == "1.3.1"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == "1.3.1"


def test_changelog_has_a_1_3_1_entry():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    # parts: [preamble, heading1, body1, heading2, body2, ...]
    assert len(parts) >= 3, text
    assert "1.3.1" in parts[1], parts[1]
    assert parts[2].strip(), "the 1.3.1 entry is empty"
