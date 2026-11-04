import pytest

from fetchkit.registry import client_for, load_registry


def write(tmp_path, text):
    path = tmp_path / "services.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_client_for_uses_the_registry_entry(tmp_path, transport, clock):
    path = write(tmp_path, '[billing]\nbase_url = "https://billing.example/v2"\ntimeout = 4\nmin_interval = 0.25\n')
    transport.reply(200, {"ok": True})
    client = client_for("billing", path=path, transport=transport, clock=clock, sleep=clock.sleep)
    assert client.get_json("invoices") == {"ok": True}
    client.get_json("invoices/2")
    assert transport.requests[0]["url"] == "https://billing.example/v2/invoices"
    assert transport.requests[0]["timeout"] == 4
    assert clock.sleeps == pytest.approx([0.25])


def test_entries_without_timings_get_the_defaults(tmp_path, transport, clock):
    path = write(tmp_path, '[ledger]\nbase_url = "https://ledger.example/v1"\n')
    transport.reply(200, {})
    client = client_for("ledger", path=path, transport=transport, clock=clock, sleep=clock.sleep)
    client.get_json("a")
    client.get_json("b")
    assert transport.requests[0]["timeout"] == 10
    assert clock.sleeps == []


def test_unknown_services_and_keys_are_refused(tmp_path):
    path = write(tmp_path, '[billing]\nbase_url = "https://billing.example/v2"\nretries = 3\n')
    with pytest.raises(ValueError, match="unknown key"):
        load_registry(path)
    with pytest.raises(KeyError, match="search"):
        client_for("search", path=write(tmp_path, '[billing]\nbase_url = "https://b.example"\n'))


def test_the_shipped_registry_names_every_service():
    services = load_registry()
    assert sorted(services) == ["billing", "inventory", "ledger", "search"]
    assert all(entry["base_url"].startswith("https://") for entry in services.values())
