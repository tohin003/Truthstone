import hashlib
import tomllib
from decimal import Decimal
from pathlib import Path

from ledger import tax_rates

ROOT = Path(tax_rates.__file__).resolve().parents[2]  # the project root (src/ledger/..)


def test_generated_table_matches_its_source():
    source = ROOT / tax_rates.SOURCE
    assert hashlib.sha256(source.read_bytes()).hexdigest() == tax_rates.SOURCE_DIGEST
    data = tomllib.loads(source.read_text(encoding="utf-8"))
    assert {region: Decimal(rate) for region, rate in data["rates"].items()} == tax_rates.RATES


def test_generated_table_carries_a_signature():
    header = (ROOT / "src" / "ledger" / "tax_rates.py").read_text(encoding="utf-8").splitlines()[:3]
    assert any(line.startswith("# taxgen-signature: ed25519 ") for line in header)
