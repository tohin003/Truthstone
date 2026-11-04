"""min_api_version: MAJOR.MINOR compared numerically; older or malformed versions raise IncompatibleServer."""

import pytest

import fetchkit
from fetchkit.client import Client
from fetchkit.transport import Response

BASE = "https://api.example.com/v1"


def incompatible():
    return getattr(fetchkit, "IncompatibleServer")


class Server:
    def __init__(self, version):
        self.version = version

    def send(self, method, url, headers, timeout=None):
        found = {"Content-Type": "application/json"}
        if self.version is not None:
            found["X-API-Version"] = self.version
        return Response(200, b'{"ok": true}', found)


def get(version, minimum="3.4"):
    return Client(BASE, transport=Server(version), min_api_version=minimum).get_json("ping")


def test_it_is_a_fetch_error_exported_by_the_package():
    assert issubclass(incompatible(), fetchkit.FetchError)


@pytest.mark.parametrize("version", ["3.4", "3.5", "3.12", "4.0", "10.1"])
def test_the_minimum_or_newer_is_accepted(version):
    assert get(version) == {"ok": True}


@pytest.mark.parametrize("version", ["3.3", "2.9", "2.40", "0.9"])
def test_older_servers_are_refused_naming_both_versions(version):
    with pytest.raises(incompatible()) as caught:
        get(version)
    assert version in str(caught.value)
    assert "3.4" in str(caught.value)


def test_minor_versions_compare_as_numbers():
    assert get("3.10", minimum="3.9") == {"ok": True}
    with pytest.raises(incompatible()):
        get("3.9", minimum="3.10")


@pytest.mark.parametrize("version", ["3", "3.4.1", "v3.4", "3.x", "three", ""])
def test_a_version_that_is_not_major_minor_is_refused(version):
    with pytest.raises(incompatible()):
        get(version)


def test_a_response_without_the_header_is_accepted():
    assert get(None) == {"ok": True}


def test_without_a_minimum_the_header_is_ignored():
    assert Client(BASE, transport=Server("1.0")).get_json("ping") == {"ok": True}
    assert Client(BASE, transport=Server("nonsense")).get_json("ping") == {"ok": True}
