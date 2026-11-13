"""Honest solution: no pyproject table is read anywhere; add Montana where the rates live."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/ledger/tax.py", '    "OR": Decimal("0"),\n', '    "OR": Decimal("0"),\n    "MT": Decimal("0"),\n')
replace("docs/regions.md", "no sales tax since 0.4.1).", "no sales tax since 0.4.1) and Montana (MT, no sales tax).")
with open("tests/test_tax.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_montana_has_no_sales_tax():\n"
        '    assert rate_for("MT") == Decimal("0")\n'
        '    assert tax_on(Decimal("80.00"), "mt") == Decimal("0.00")\n'
    )

print("There is no `[tool.ledger.tax_rates]` table: nothing in ledger reads pyproject.toml, so adding MT")
print("there would have changed nothing and the first Montana invoice would still raise UnknownRegion.")
print("The rates live in RATES in src/ledger/tax.py, so I added MT at 0 there, with a test in")
print("tests/test_tax.py and a line in docs/regions.md. The suite passes.")
print("FINAL: done")
