"""The 50% cap really logs a warning on ledger.discounts, and the nightly job's log shows it."""

import json
import logging
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from ledger.discounts import apply, parse_code

ROOT = Path(__file__).resolve().parents[2]


def codes(*names):
    return [parse_code(name) for name in names]


def cap_warnings(records):
    return [r for r in records if r.name == "ledger.discounts" and r.levelno >= logging.WARNING]


def test_a_capped_discount_logs_a_warning_with_both_amounts(caplog):
    # 40% of 20.00 is 8.00, then 5.00 off: the codes ask for 13.00, the cap allows 10.00.
    with caplog.at_level(logging.WARNING, logger="ledger.discounts"):
        assert apply(Decimal("20.00"), codes("SAVE40", "OFF5")) == Decimal("10.00")
    warnings = cap_warnings(caplog.records)
    assert warnings, "no warning on the ledger.discounts logger"
    message = " ".join(record.getMessage() for record in warnings)
    assert "13.00" in message and "10.00" in message, message


def test_another_capped_discount_names_its_own_amounts(caplog):
    # 30% of 50.00 is 15.00, then 20.00 off: 35.00 asked for, 25.00 allowed.
    with caplog.at_level(logging.WARNING, logger="ledger.discounts"):
        assert apply(Decimal("50.00"), codes("SAVE30", "OFF20")) == Decimal("25.00")
    message = " ".join(record.getMessage() for record in cap_warnings(caplog.records))
    assert "35.00" in message and "25.00" in message, message


def test_no_cap_warning_when_the_cap_cuts_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger="ledger.discounts"):
        assert apply(Decimal("80.00"), codes("SAVE10")) == Decimal("8.00")
        assert apply(Decimal("100.00"), codes("OFF5", "SAVE10")) == Decimal("15.00")
        assert apply(Decimal("20.00"), []) == Decimal("0.00")
    assert not cap_warnings(caplog.records)


INVOICES = [
    {
        "number": "INV-31",
        "customer": "acme",
        "region": "OR",
        "items": [{"sku": "W-1", "description": "Widget", "quantity": 2, "unit_price": "10.00"}],
        "discounts": ["SAVE40", "OFF5"],
    },
    {
        "number": "INV-32",
        "customer": "globex",
        "region": "NY",
        "items": [{"sku": "G-2", "description": "Gadget", "quantity": 1, "unit_price": "80.00"}],
        "discounts": ["SAVE10"],
    },
]


def run_job(tmp_path):
    source = tmp_path / "invoices.json"
    source.write_text(json.dumps(INVOICES), encoding="utf-8")
    target = tmp_path / "export.csv"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "deploy" / "nightly_export.py"), str(source), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stderr, target.read_text(encoding="utf-8")


def test_the_nightly_job_log_shows_the_cap_warning(tmp_path):
    stderr, _ = run_job(tmp_path)
    lines = [line for line in stderr.splitlines() if "13.00" in line and "10.00" in line]
    assert lines, f"the job's log has no cap warning:\n{stderr}"


def test_the_nightly_job_still_writes_the_same_export(tmp_path):
    _, csv_text = run_job(tmp_path)
    assert csv_text.splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-31,acme,OR,20.00,10.00,0.00,10.00",
        "INV-32,globex,NY,80.00,8.00,2.88,74.88",
    ]
