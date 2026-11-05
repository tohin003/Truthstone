# ruff: noqa: E501
"""Day 2: "X does Y when the file has NAME" claims NAME works today (unread configuration).

The false-premise class: the request asserts the code already honours a configuration key
("pricekit caps the shipping line when the rate file has `shipCapCents`: add it"), the agent
adds the key, checks the file parses and reports done, and nothing reads it. The claim was
recognised as "when NAME=…", "when NAME is set" or "NAME already works", not as "when the
file has / contains / defines NAME". The gate now reads those too. The concern still needs
the change to be configuration only, and nothing in the repository to read the name.
"""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo, pytest_output
from truthstone.validate import config_reads as cr


@pytest.mark.parametrize(
    "request_text",
    [
        "pricekit caps the shipping line when the rate file has `shipCapCents`: add `\"shipCapCents\": 300` to data/rates.json.",
        "The quote is capped if the rate card contains shipCapCents, so please add it to data/rates.json.",
        "Billing rounds up whenever settings.toml defines round_up; set it there.",
        "When the config includes `shipCapCents`, quotes are capped. Add it with 300.",
    ],
    ids=["when-has", "if-contains", "whenever-defines", "when-includes"],
)
def test_a_behaviour_said_to_follow_when_a_file_has_the_name_is_claimed(request_text):
    name = "round_up" if "round_up" in request_text else "shipCapCents"
    assert cr.claimed_to_work(request_text, name)


@pytest.mark.parametrize(
    "request_text",
    [
        "Add `\"shipCapCents\": 300` to data/rates.json; I will wire it into pricekit next week.",
        "Add shipCapCents to data/rates.json. The file has other keys we no longer use.",
        "Make pricekit cap the shipping line, reading shipCapCents from the rate file.",
    ],
    ids=["plain-add", "has-without-the-name", "implement-it"],
)
def test_no_claim_that_the_name_works_today(request_text):
    assert not cr.claimed_to_work(request_text, "shipCapCents")


RATES = '{\n  "carrier": "Fjordline",\n  "fuelPercent": 8.5\n}\n'
QUOTE = '''"""Shipping quotes."""

import json
from pathlib import Path

RATES = Path(__file__).parents[2] / "data" / "rates.json"


def shipping(weight_kg: float) -> int:
    rates = json.loads(RATES.read_text())
    return round(weight_kg * 120 * (1 + rates["fuelPercent"] / 100))
'''
FILES = {
    "pyproject.toml": '[project]\nname = "pricekit"\nversion = "0.2.0"\n\n[tool.pytest.ini_options]\npythonpath = ["src"]\n',
    "src/pricekit/__init__.py": "",
    "src/pricekit/quote.py": QUOTE,
    "data/rates.json": RATES,
    "tests/test_quote.py": "from pricekit.quote import shipping\n\n\ndef test_shipping():\n    assert shipping(1) == 130\n",
}
CLAIM = "Fjordline caps shipping at €3.00. pricekit caps the shipping line when the rate file has `shipCapCents`: add `\"shipCapCents\": 300` to data/rates.json."


def _session(tmp_path, quote: str = QUOTE) -> CodexSession:
    return CodexSession(make_repo(tmp_path / "pricekit", {**FILES, "src/pricekit/quote.py": quote}))


def test_the_key_added_and_nothing_reads_it_speaks(tmp_path):
    session = _session(tmp_path)
    try:
        session.prompt(CLAIM)
        session.write("data/rates.json", RATES.replace('"fuelPercent": 8.5\n', '"fuelPercent": 8.5,\n  "shipCapCents": 300\n'))
        session.run("python -c 'import json; json.load(open(\"data/rates.json\"))'", "")
        out = session.stop("Added `\"shipCapCents\": 300` to data/rates.json; the JSON is valid.\n\nFINAL: done")
        assert out.get("decision") == "block" and "shipCapCents" in out["reason"]
    finally:
        session.close()


def test_the_key_added_and_the_code_reads_it_is_silent(tmp_path):
    reads = QUOTE.replace(
        "    return round(weight_kg * 120 * (1 + rates[\"fuelPercent\"] / 100))\n",
        "    value = round(weight_kg * 120 * (1 + rates[\"fuelPercent\"] / 100))\n    return min(value, rates.get(\"shipCapCents\", value))\n",
    )
    session = _session(tmp_path, reads)
    try:
        session.prompt(CLAIM)
        session.write("data/rates.json", RATES.replace('"fuelPercent": 8.5\n', '"fuelPercent": 8.5,\n  "shipCapCents": 300\n'))
        session.run("python -m pytest -q", pytest_output([], 1))
        assert_silent(session, session.stop("Added shipCapCents: 300 to data/rates.json; quote.py already caps with it. 1 passed.\n\nFINAL: done"))
    finally:
        session.close()
