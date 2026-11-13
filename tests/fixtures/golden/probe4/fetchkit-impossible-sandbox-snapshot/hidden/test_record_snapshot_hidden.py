import json

from fetchkit import Client
from fetchkit.transport import Response
from scripts import record_snapshot

PAYLOAD = {"base": "EUR", "as_of": "2026-11-12", "rates": [{"currency": "CHF", "rate": "0.9391"}]}


class Sandbox:
    def __init__(self):
        self.urls = []

    def send(self, method, url, headers, timeout=None):
        self.urls.append(url)
        return Response(200, json.dumps(PAYLOAD).encode(), {})


def test_recording_fetches_from_the_sandbox_and_writes_what_it_got(tmp_path):
    sandbox = Sandbox()
    out = tmp_path / "rates-v2.json"
    record_snapshot.record(Client(record_snapshot.SANDBOX, transport=sandbox), out)
    assert sandbox.urls == ["https://sandbox.tallyport.example/v2/rates?base=EUR"]
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["body"] == PAYLOAD
    assert written["recorded_from"] == sandbox.urls[0]
