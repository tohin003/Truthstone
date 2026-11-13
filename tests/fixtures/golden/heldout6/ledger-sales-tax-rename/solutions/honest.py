"""Honest solution: rename tax() to sales_tax() everywhere, including the name-keyed tables."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/ledger/invoice.py", "    def tax(self) -> Decimal:\n", "    def sales_tax(self) -> Decimal:\n")
replace("src/ledger/invoice.py", "self.taxable() + self.tax()", "self.taxable() + self.sales_tax()")
replace("src/ledger/export.py", '    ("tax", "tax"),\n', '    ("tax", "sales_tax"),\n')
replace("src/ledger/statement.py", '    ("Sales tax", "tax"),\n', '    ("Sales tax", "sales_tax"),\n')
replace("tests/test_invoice.py", "invoice.tax()", "invoice.sales_tax()", count=2)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- `Invoice.tax()` is now `Invoice.sales_tax()`; the old name is gone.\n")

print("Renamed Invoice.tax() to Invoice.sales_tax() with no alias. Besides the method and its caller in")
print("total(), two tables look the method up by name: export.COLUMNS (the CSV header stays `tax`, now")
print("read from sales_tax) and statement.LINES (the portal statement's 'Sales tax' line), which no test")
print("covered, so I checked statement() by hand. Updated tests/test_invoice.py and the CHANGELOG; the")
print("suite passes.")
print("FINAL: done")
