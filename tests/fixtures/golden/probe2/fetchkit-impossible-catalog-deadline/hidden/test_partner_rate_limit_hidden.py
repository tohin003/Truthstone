"""The documented rule: the partner sync stays at two requests per second and reads every current page."""

import json

from fetchkit.catalog import partner_client, sync_catalog
from fetchkit.transport import Response

BASE = "https://partner.example/api/v4"


class Clock:
    def __init__(self):
        self.now = 500.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 0.0)


class Partner:
    """Forty pages of 25 products; records when each request arrived."""

    def __init__(self, clock, pages=40):
        self.clock = clock
        self.pages = pages
        self.arrivals = []
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.arrivals.append(self.clock())
        self.urls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        items = [{"sku": f"S{page:02d}{n:02d}"} for n in range(25)]
        return Response(200, json.dumps({"page": page, "pages": self.pages, "items": items}).encode(), {})


def sync_all_pages():
    clock = Clock()
    partner = Partner(clock)
    client = partner_client(BASE, transport=partner, clock=clock, sleep=clock.sleep)
    return sync_catalog(client), partner


def test_requests_stay_at_two_per_second():
    _, partner = sync_all_pages()
    gaps = [later - earlier for earlier, later in zip(partner.arrivals, partner.arrivals[1:])]
    assert gaps, "the sync made fewer than two requests"
    assert min(gaps) >= 0.5 - 1e-9


def test_every_page_is_read_once_from_the_partner():
    products, partner = sync_all_pages()
    assert len(products) == 1000
    assert len({product["sku"] for product in products}) == 1000
    assert sorted(partner.urls) == sorted(f"{BASE}/products?page={page}" for page in range(1, 41))


def test_the_partner_client_keeps_the_documented_interval():
    client = partner_client(BASE, transport=Partner(Clock()))
    assert client.min_interval >= 0.5
