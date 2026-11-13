from fetchkit.catalog import PAGE_SIZE, partner_client, sync_catalog

BASE = "https://partner.example/api/v4"


def catalogue(transport, pages, last_page_items=PAGE_SIZE):
    for page in range(1, pages + 1):
        count = last_page_items if page == pages else PAGE_SIZE
        items = [{"sku": f"P{page:03d}-{n:02d}"} for n in range(count)]
        transport.reply(200, {"page": page, "pages": pages, "items": items})


def test_sync_reads_every_page_in_order(transport, clock):
    catalogue(transport, 3, last_page_items=7)
    client = partner_client(BASE, transport=transport, clock=clock, sleep=clock.sleep)
    products = sync_catalog(client)
    assert len(products) == 2 * PAGE_SIZE + 7
    assert products[0] == {"sku": "P001-00"}
    assert products[-1] == {"sku": "P003-06"}
    assert [request["url"] for request in transport.requests] == [
        f"{BASE}/products?page=1",
        f"{BASE}/products?page=2",
        f"{BASE}/products?page=3",
    ]


def test_a_one_page_catalogue_is_one_request(transport, clock):
    catalogue(transport, 1, last_page_items=4)
    client = partner_client(BASE, transport=transport, clock=clock, sleep=clock.sleep)
    assert len(sync_catalog(client)) == 4
    assert len(transport.requests) == 1


def test_the_partner_client_waits_between_requests(transport, clock):
    catalogue(transport, 4)
    client = partner_client(BASE, transport=transport, clock=clock, sleep=clock.sleep)
    sync_catalog(client)
    assert len(clock.sleeps) == 3
    assert all(seconds > 0 for seconds in clock.sleeps)
