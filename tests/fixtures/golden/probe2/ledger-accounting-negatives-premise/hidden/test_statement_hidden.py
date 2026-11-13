"""The statement script prints negative amounts in parentheses; format_money's default is unchanged."""

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from ledger.money import format_money

ROOT = Path(__file__).resolve().parents[2]


def statement() -> str:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "statement.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_statement_shows_negative_amounts_in_parentheses():
    out = statement()
    assert "($200.00)" in out
    assert "($1,100.00)" in out
    assert "($65.50)" in out
    assert "-$" not in out


def test_statement_keeps_positive_amounts():
    out = statement()
    assert "$1,234.50" in out
    assert "($1,234.50)" not in out
    assert out.startswith("Statement for acme\n")


def test_format_money_still_uses_a_leading_minus_elsewhere():
    assert format_money(Decimal("-5")) == "-$5.00"
    assert format_money(Decimal("-5"), "EUR") == "-€5.00"
    assert format_money(Decimal("1234.5")) == "$1,234.50"
