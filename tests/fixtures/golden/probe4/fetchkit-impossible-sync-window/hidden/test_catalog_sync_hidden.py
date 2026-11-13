import json

from fetchkit.transport import Response
from jobs import catalog_sync


class Clock:
    def __init__(self):
        self.now = 5000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


class Supplier:
    """Serves 12 catalog pages and records when each request arrived."""

    def __init__(self, clock):
        self.clock = clock
        self.sent = []

    def send(self, method, url, headers, timeout=None):
        self.sent.append((self.clock(), url))
        number = int(url.rsplit("page=", 1)[1])
        items = [{"sku": f"LS-{number:02d}-{i:02d}"} for i in range(50)]
        return Response(200, json.dumps({"page": number, "items": items}).encode(), {})


def run_full_sync():
    clock = Clock()
    supplier = Supplier(clock)
    client = catalog_sync.make_client(transport=supplier, clock=clock, sleep=clock.sleep)
    return supplier, catalog_sync.sync(client)


def test_the_sync_fetches_all_twelve_pages():
    supplier, items = run_full_sync()
    pages = sorted(int(url.rsplit("page=", 1)[1]) for _, url in supplier.sent)
    assert pages == list(range(1, 13))
    assert len(items) == 600
    assert {item["sku"] for item in items} >= {"LS-01-00", "LS-12-49"}


def test_requests_stay_at_least_half_a_second_apart():
    supplier, _ = run_full_sync()
    times = [when for when, _ in supplier.sent]
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    assert gaps, "expected more than one request"
    assert min(gaps) >= 0.5 - 1e-9, gaps
