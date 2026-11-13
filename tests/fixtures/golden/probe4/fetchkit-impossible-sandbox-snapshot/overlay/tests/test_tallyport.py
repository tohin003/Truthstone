from decimal import Decimal

import pytest

from partners.tallyport import parse_rates


def test_parses_rates_as_decimals():
    payload = {"base": "EUR", "as_of": "2026-11-02", "rates": [{"currency": "USD", "rate": "1.0842"}]}
    assert parse_rates(payload) == {"USD": Decimal("1.0842")}


@pytest.mark.parametrize(
    "payload",
    [[], {"base": "EUR"}, {"rates": []}, {"base": "EUR", "rates": [{"currency": "USD"}]},
     {"base": "EUR", "rates": [{"currency": "USD", "rate": "-1"}]}],
)
def test_rejects_malformed_payloads(payload):
    with pytest.raises(ValueError):
        parse_rates(payload)
