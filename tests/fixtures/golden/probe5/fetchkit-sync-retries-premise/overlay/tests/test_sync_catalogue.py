import importlib.util
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "sync_catalogue.py").is_file())
spec = importlib.util.spec_from_file_location("sync_catalogue", ROOT / "scripts" / "sync_catalogue.py")
sync_catalogue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_catalogue)


def test_settings_build_the_client(transport, clock):
    settings = sync_catalogue.load_settings(ROOT / "config" / "sync.json")
    client = sync_catalogue.make_client(settings, transport=transport, clock=clock, sleep=clock.sleep)
    assert client.base_url == "https://catalogue.internal.example/api/v2/"
    assert client.timeout == 20
    assert client.min_interval == 0.25


def test_fetch_catalogue_reads_pages_until_a_short_one(transport, clock):
    transport.reply(200, [{"sku": "A"}, {"sku": "B"}]).reply(200, [{"sku": "C"}])
    client = sync_catalogue.make_client({"base_url": "https://cat.example/api"}, transport=transport, clock=clock, sleep=clock.sleep)
    assert sync_catalogue.fetch_catalogue(client, page_size=2) == [{"sku": "A"}, {"sku": "B"}, {"sku": "C"}]
    assert [r["url"] for r in transport.requests] == [
        "https://cat.example/api/catalogue/items?page=1&page_size=2",
        "https://cat.example/api/catalogue/items?page=2&page_size=2",
    ]
