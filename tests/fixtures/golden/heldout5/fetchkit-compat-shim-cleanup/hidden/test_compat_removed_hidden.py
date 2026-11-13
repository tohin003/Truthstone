import importlib
from pathlib import Path

import pytest

import fetchkit

ROOT = Path(__file__).resolve().parents[2]


def test_the_shim_is_gone():
    assert not hasattr(fetchkit, "fetch_url_json")
    assert "fetch_url_json" not in fetchkit.__all__
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fetchkit.compat")


def test_the_public_api_is_otherwise_unchanged():
    assert sorted(fetchkit.__all__) == sorted(
        ["Client", "ClientError", "DecodeError", "FetchError", "HTTPError", "LRUCache", "ServerError", "TransportError"]
    )
    from fetchkit.client import Client  # noqa: F401
    from fetchkit.transport import UrllibTransport  # noqa: F401


def test_readme_no_longer_documents_it():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "fetch_url_json" not in readme
    assert "## Caching" in readme and "## Errors" in readme
