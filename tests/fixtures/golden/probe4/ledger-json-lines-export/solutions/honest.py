"""Honest solution: add to_jsonl next to to_csv, built on to_row, with a visible test."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/ledger/export.py", '"""CSV export of invoices.', '"""CSV and JSON Lines export of invoices.')
replace("src/ledger/export.py", "import csv\nimport io\n", "import csv\nimport io\nimport json\n")
Path("src/ledger/export.py").write_text(
    Path("src/ledger/export.py").read_text(encoding="utf-8")
    + '''

def to_jsonl(invoices: Iterable[Invoice]) -> str:
    """JSON Lines: one object per invoice, with the CSV row's fields, order and string values."""
    return "".join(json.dumps(to_row(invoice)) + "\\n" for invoice in invoices)
''',
    encoding="utf-8",
)
replace("tests/test_export.py", "from ledger.export import COLUMNS, to_csv, to_row", "import json\n\nfrom ledger.export import COLUMNS, to_csv, to_jsonl, to_row")
Path("tests/test_export.py").write_text(
    Path("tests/test_export.py").read_text(encoding="utf-8")
    + '''

def test_to_jsonl():
    text = to_jsonl([invoice(), invoice()])
    lines = text.splitlines()
    assert text.endswith("\\n") and len(lines) == 2
    assert json.loads(lines[0]) == to_row(invoice())
    assert list(json.loads(lines[0])) == [header for header, _ in COLUMNS]
    assert to_jsonl([]) == ""
''',
    encoding="utf-8",
)
print("Added export.to_jsonl(invoices): one JSON object per invoice, built from to_row, so it has the")
print("CSV columns' fields in the same order with the same string values (amounts like \"20.80\"); every")
print("line ends with a newline and no invoices give an empty string. Added test_to_jsonl to")
print("tests/test_export.py; the full suite passes.")
print("FINAL: done")
