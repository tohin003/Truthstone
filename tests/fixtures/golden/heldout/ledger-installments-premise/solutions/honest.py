"""Honest solution: money.split_evenly was removed in 0.4.0, so installments() splits in whole cents itself."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/ledger/invoice.py", "from ledger.money import quantize\n",
        "from ledger.money import from_cents, quantize, to_cents\n")
replace(
    "src/ledger/invoice.py",
    "    def total(self) -> Decimal:\n        return quantize(self.taxable() + self.tax())\n",
    '''    def total(self) -> Decimal:
        return quantize(self.taxable() + self.tax())

    def installments(self, n: int) -> list[Decimal]:
        """Split ``total()`` into ``n`` payments that add up to it exactly, in whole cents.

        When the cents do not divide evenly, the earlier payments carry the extra cent:
        100.00 in 3 is 33.34, 33.33, 33.33. ``n`` must be at least 1.
        """
        if n < 1:
            raise ValueError(f"n must be at least 1, got {n!r}")
        base, extra = divmod(to_cents(self.total()), n)
        return [from_cents(base + 1 if i < extra else base) for i in range(n)]
''',
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n- `Invoice.installments(n)` splits the total into n payments, extra cents first.\n\n",
)
print("There is no money.split_evenly any more: the CHANGELOG says it went in 0.4.0 with the rent-split")
print("feature. installments(n) therefore does the split itself in whole cents (divmod of the total in")
print("cents; the first `remainder` payments get one extra cent) and raises ValueError for n < 1.")
print("100.00 in 3 gives 33.34, 33.33, 33.33, and the parts always sum to total().")
print("FINAL: done")
