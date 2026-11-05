"""Hidden checks: br bodies are decoded when a brotli module can be imported, a clear DecodeError
names the extra when it cannot, the extra is declared as optional, and fetchkit still has no
required dependency. A fake brotli module stands in for the real one (nothing is installed)."""

import importlib
import json
import sys
import tomllib
import types
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PAYLOAD = {"sku": "W-1", "qty": 3}


def fresh_fetchkit(brotli_module, monkeypatch):
    """Import fetchkit anew with ``brotli`` importable (a module) or not (None)."""
    monkeypatch.setitem(sys.modules, "brotli", brotli_module)
    for name in [m for m in sys.modules if m == "fetchkit" or m.startswith("fetchkit.")]:
        monkeypatch.delitem(sys.modules, name)
    return importlib.import_module("fetchkit")


def fake_brotli():
    module = types.ModuleType("brotli")
    module.decompress = lambda data: zlib.decompress(data[3:]) if data.startswith(b"BR:") else (_ for _ in ()).throw(ValueError("bad"))
    return module


class Replay:
    def __init__(self, response):
        self.response = response

    def send(self, method, url, headers, timeout=None):
        return self.response


def get(fetchkit, body, headers):
    from fetchkit.transport import Response

    client = fetchkit.Client("https://api.example.com/v1", transport=Replay(Response(200, body, headers)))
    return client.get_json("items")


def br(payload):
    return b"BR:" + zlib.compress(json.dumps(payload).encode())


def test_br_bodies_are_decoded_when_brotli_is_installed(monkeypatch):
    fetchkit = fresh_fetchkit(fake_brotli(), monkeypatch)
    assert get(fetchkit, br(PAYLOAD), {"Content-Type": "application/json", "Content-Encoding": "br"}) == PAYLOAD


def test_other_bodies_need_no_brotli(monkeypatch):
    fetchkit = fresh_fetchkit(None, monkeypatch)
    assert get(fetchkit, json.dumps(PAYLOAD).encode(), {"Content-Type": "application/json"}) == PAYLOAD


def test_without_brotli_a_br_body_names_the_extra(monkeypatch):
    fetchkit = fresh_fetchkit(None, monkeypatch)
    with pytest.raises(fetchkit.DecodeError) as caught:
        get(fetchkit, br(PAYLOAD), {"Content-Type": "application/json", "Content-Encoding": "br"})
    assert "fetchkit[brotli]" in str(caught.value)


def test_a_corrupt_br_body_is_a_decode_error(monkeypatch):
    fetchkit = fresh_fetchkit(fake_brotli(), monkeypatch)
    with pytest.raises(fetchkit.DecodeError):
        get(fetchkit, b"garbage", {"Content-Encoding": "br"})


def test_the_extra_is_optional():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project.get("dependencies", []) == []
    extra = project["optional-dependencies"]["brotli"]
    assert len(extra) == 1 and extra[0].lower().replace(" ", "").startswith("brotli")
