"""totals_row = true under [export] in ledger.toml really ends the export with the TOTAL row."""

import csv
import io
import os
import shutil
import subprocess
import sys
import tomllib
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = """
from decimal import Decimal
from ledger.discounts import parse_code
from ledger.export import to_csv
from ledger.invoice import Invoice, LineItem

batch = [
    Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("19.99"))], [parse_code("SAVE10")]),
    Invoice(
        "INV-2",
        "globex",
        "NY",
        [LineItem("G-2", "Gadget", 1, Decimal("45.50")), LineItem("W-1", "Widget", 2, Decimal("19.99"))],
    ),
    Invoice("INV-3", "initech", "OR", [LineItem("S-3", "Sprocket", 4, Decimal("2.25"))], [parse_code("OFF5")]),
]
print(to_csv(batch), end="")
"""

HEADER = ["number", "customer", "region", "subtotal", "discount", "tax", "total"]
SUMMED = range(3, 7)


def export(tmp_path: Path, settings_text: str) -> list[list[str]]:
    """Export the batch in a fresh interpreter, from a copy of the code with this ledger.toml."""
    project = tmp_path / "project"
    shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (project / "ledger.toml").write_text(settings_text, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=project, env=env, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    return list(csv.reader(io.StringIO(proc.stdout)))


def test_the_totals_row_holds_the_column_sums(tmp_path):
    rows = export(tmp_path, '[export]\ndelimiter = ","\ntotals_row = true\n')
    assert rows[0] == HEADER
    assert [row[0] for row in rows[1:]] == ["INV-1", "INV-2", "INV-3", "TOTAL"]
    total = rows[-1]
    assert len(total) == 7 and total[1:3] == ["", ""], total
    for column in SUMMED:
        expected = sum((Decimal(row[column]) for row in rows[1:-1]), Decimal("0"))
        assert Decimal(total[column]) == expected, (HEADER[column], total[column], expected)


def test_no_totals_row_without_the_setting(tmp_path):
    rows = export(tmp_path, '[export]\ndelimiter = ","\n')
    assert rows[0] == HEADER
    assert [row[0] for row in rows[1:]] == ["INV-1", "INV-2", "INV-3"]


def test_no_totals_row_when_it_is_off(tmp_path):
    rows = export(tmp_path, '[export]\ndelimiter = ","\ntotals_row = false\n')
    assert [row[0] for row in rows[1:]] == ["INV-1", "INV-2", "INV-3"]


def test_ledger_toml_switches_it_on():
    with open(ROOT / "ledger.toml", "rb") as handle:
        settings = tomllib.load(handle)
    assert settings.get("export", {}).get("totals_row") is True
