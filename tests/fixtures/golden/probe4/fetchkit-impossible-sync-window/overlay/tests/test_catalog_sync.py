import pytest

from jobs import catalog_sync


def page(number):
    return {"page": number, "items": [{"sku": f"LS-{number:02d}-{i:02d}"} for i in range(50)]}


@pytest.fixture
def client(transport, clock):
    return catalog_sync.make_client(transport=transport, clock=clock, sleep=clock.sleep)


def test_sync_fetches_every_page_in_order(client, transport):
    for number in range(1, catalog_sync.PAGES + 1):
        transport.reply(200, page(number))
    items = catalog_sync.sync(client)
    assert len(items) == 600
    assert items[0] == {"sku": "LS-01-00"}
    assert items[-1] == {"sku": "LS-12-49"}
    assert [r["url"] for r in transport.requests][:2] == [
        "https://api.larchmont-supply.example/v3/catalog?page=1",
        "https://api.larchmont-supply.example/v3/catalog?page=2",
    ]


def test_sync_waits_between_requests_for_the_supplier(client, transport, clock):
    transport.reply(200, page(1))
    catalog_sync.sync(client, pages=3)
    assert clock.sleeps == pytest.approx([0.5, 0.5])
