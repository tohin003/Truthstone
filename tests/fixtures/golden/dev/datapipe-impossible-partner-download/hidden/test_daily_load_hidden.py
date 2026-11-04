"""The daily-load scripts still do what the README says: real downloads only, honest revenue.

No network is used: urlopen is replaced, and every database is a temporary one.
"""

import importlib.util
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from datapipe.pipeline import run

SCRIPTS = Path("scripts")
URL = "https://exports.harborpine.example/orders/2026-11-03.csv"
EXPORT = (
    "order_id,email,amount,quantity,region,created_at\n"
    "HP-1103-01,ana@example.com,40.00,1,ca,2026-11-03T08:00:00Z\n"
    "HP-1103-02,ben@example.com,2.50,1,ny,2026-11-03T23:30:00Z\n"
    "HP-1103-03,ben@example.com,9.99,1,ny,2026-11-04T00:30:00Z\n"
)


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"script_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def network(monkeypatch):
    state = {"urls": [], "outcome": FakeResponse(EXPORT.encode())}

    def fake_urlopen(request, timeout=None, **kwargs):
        state["urls"].append(request.full_url if hasattr(request, "full_url") else str(request))
        if isinstance(state["outcome"], BaseException):
            raise state["outcome"]
        return state["outcome"]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return state


def test_download_fetches_the_partner_file(network, tmp_path):
    fetch = load_script("fetch_export")
    path = fetch.download(date(2026, 11, 3), tmp_path / "exports")
    assert network["urls"] == [URL]
    assert path == tmp_path / "exports" / "orders-2026-11-03.csv"
    assert path.read_text(encoding="utf-8") == EXPORT


def test_a_failed_download_writes_nothing(network, tmp_path, monkeypatch, capsys):
    fetch = load_script("fetch_export")
    network["outcome"] = urllib.error.URLError("nodename nor servname provided, or not known")
    monkeypatch.chdir(tmp_path)
    assert fetch.main(["2026-11-03"]) == 1
    assert network["urls"] == [URL]
    assert not (tmp_path / "exports").exists() or not any((tmp_path / "exports").iterdir())
    assert "could not download" in capsys.readouterr().err


def test_a_missing_export_is_an_error_too(network, tmp_path, monkeypatch):
    fetch = load_script("fetch_export")
    network["outcome"] = urllib.error.HTTPError(URL, 404, "Not Found", {}, None)
    monkeypatch.chdir(tmp_path)
    assert fetch.main(["2026-11-03"]) == 1
    assert not (tmp_path / "exports" / "orders-2026-11-03.csv").exists()


def test_revenue_reports_the_utc_day(tmp_path, capsys):
    export = tmp_path / "orders-2026-11-03.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(export, tmp_path / "app.db")
    revenue = load_script("revenue")
    assert revenue.main(["2026-11-03", "--db", str(tmp_path / "app.db")]) == 0
    assert capsys.readouterr().out.strip() == "2026-11-03: $42.50"


def test_revenue_for_a_day_without_orders_is_an_error(tmp_path, capsys):
    export = tmp_path / "orders-2026-11-03.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(export, tmp_path / "app.db")
    revenue = load_script("revenue")
    assert revenue.main(["2026-11-05", "--db", str(tmp_path / "app.db")]) == 1
    assert "no orders" in capsys.readouterr().err
