from pathlib import Path

import pytest

import fetchkit
from fetchkit.cache import LRUCache
from fetchkit.config import ConfigError, client_from_config, load_settings
from fetchkit.transport import DEFAULT_TIMEOUT

# the repository root, found through the package (src/fetchkit/__init__.py)
ROOT = Path(fetchkit.__file__).resolve().parents[2]


def write(tmp_path, text):
    path = tmp_path / "service.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_the_client_section(tmp_path, transport):
    path = write(
        tmp_path,
        '[client]\nbase_url = "https://api.example.com/v1"\ntimeout = 2.5\nmin_interval = 0.5\n',
    )
    client = client_from_config(path, transport=transport)
    assert client.base_url == "https://api.example.com/v1/"
    assert client.timeout == 2.5
    assert client.min_interval == 0.5
    assert client.cache is None


def test_defaults(tmp_path):
    client = client_from_config(write(tmp_path, '[client]\nbase_url = "https://api.example.com"\n'))
    assert client.timeout == DEFAULT_TIMEOUT
    assert client.min_interval == 0.0
    assert client.headers == {"Accept": "application/json"}


def test_headers_table_is_sent(tmp_path, transport):
    path = write(
        tmp_path,
        '[client]\nbase_url = "https://api.example.com"\n\n[client.headers]\nX-Team = "pricing"\n',
    )
    transport.reply(200, {})
    client_from_config(path, transport=transport).get_json("ping")
    assert transport.requests[0]["headers"] == {"Accept": "application/json", "X-Team": "pricing"}


def test_cache_size_builds_a_cache(tmp_path):
    client = client_from_config(write(tmp_path, '[client]\nbase_url = "https://a.example"\ncache_size = 4\n'))
    assert isinstance(client.cache, LRUCache)
    assert client.cache.maxsize == 4


def test_base_url_is_required(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(write(tmp_path, "[client]\ntimeout = 1.0\n"))
    with pytest.raises(ConfigError):
        load_settings(write(tmp_path, '[sync]\nbase_url = "https://a.example"\n'))


def test_service_configs_load():
    inventory = client_from_config(ROOT / "config" / "inventory.toml")
    assert inventory.base_url == "https://stock.partner-warehouse.example/api/v2/"
    pricing = client_from_config(ROOT / "config" / "pricing.toml")
    assert pricing.headers["X-Team"] == "pricing"
