import json
from pathlib import Path

import pytest

from partners.tallyport import parse_rates

SNAPSHOT = Path(__file__).parent / "snapshots" / "rates-v2.json"


@pytest.fixture
def snapshot():
    if not SNAPSHOT.exists():
        pytest.skip("no recorded snapshot yet: run scripts/record_snapshot.py (needs Tallyport's sandbox)")
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_was_recorded_from_the_sandbox(snapshot):
    assert snapshot["recorded_from"].startswith("https://sandbox.tallyport.example/v2/rates")


def test_parser_reads_the_recorded_response(snapshot):
    rates = parse_rates(snapshot["body"])
    assert rates, "the sandbox returned no rates"
    assert all(len(currency) == 3 for currency in rates)
