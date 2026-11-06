import json

from catalog import catalog_client, export_catalog
from fetchkit.transport import Response

BASE = "https://catalog.internal/v2"


class Pages:
    """Stands in for the catalogue service: serves the given pages."""

    def __init__(self, pages):
        self.pages = pages

    def send(self, method, url, headers, timeout=None):
        page = int(url.rsplit("page=", 1)[1])
        body = {"items": self.pages[page - 1], "more": page < len(self.pages)}
        return Response(200, json.dumps(body).encode())


def test_exports_every_page_and_audits_each_request():
    log = []
    client = catalog_client(BASE, log, inner=Pages([[{"sku": "D-1"}, {"sku": "D-2"}], [{"sku": "L-2"}]]))
    assert export_catalog(client) == [{"sku": "D-1"}, {"sku": "D-2"}, {"sku": "L-2"}]
    assert log == [f"GET {BASE}/products?page=1 -> 200", f"GET {BASE}/products?page=2 -> 200"]


def test_a_repeated_export_is_served_from_the_cache():
    log = []
    client = catalog_client(BASE, log, inner=Pages([[{"sku": "D-1"}]]))
    export_catalog(client)
    assert export_catalog(client) == [{"sku": "D-1"}]
    assert len(log) == 1
