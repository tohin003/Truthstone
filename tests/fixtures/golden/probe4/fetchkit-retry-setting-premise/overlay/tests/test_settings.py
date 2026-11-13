import json
from pathlib import Path

import pytest

import fetchkit
from fetchkit.cache import LRUCache
from fetchkit.settings import client_from_settings, load_settings

PARTNER = Path(fetchkit.__file__).resolve().parents[2] / "config" / "partner.json"


def write(tmp_path, settings):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def test_partner_settings_build_a_client():
    client = client_from_settings(PARTNER)
    assert client.base_url == "https://api.northwind-parts.example/v2/"
    assert client.timeout == 8.0
    assert client.min_interval == 0.2
    assert isinstance(client.cache, LRUCache) and client.cache.maxsize == 128
    assert client.headers["X-Client"] == "fetchkit"


def test_unknown_keys_are_left_for_other_tools(tmp_path):
    path = write(tmp_path, {"base_url": "https://api.example.com", "owner": "me", "alert_channel": "#x"})
    assert load_settings(path)["owner"] == "me"
    assert client_from_settings(path).base_url == "https://api.example.com/"


def test_base_url_is_required(tmp_path):
    with pytest.raises(ValueError):
        load_settings(write(tmp_path, {"timeout": 3}))


def test_overrides_win(tmp_path, transport):
    path = write(tmp_path, {"base_url": "https://api.example.com", "timeout": 8})
    client = client_from_settings(path, transport=transport, timeout=1.0)
    transport.reply(200, {"ok": True})
    assert client.get_json("ping") == {"ok": True}
    assert transport.requests[0]["timeout"] == 1.0
