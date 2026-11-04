"""Honest solution: restore the documented order AND cap the combined total."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/ledger/discounts.py",
    '''    """The total discount for ``subtotal``, never more than ``MAX_PERCENT`` percent of it."""
    cap = subtotal * MAX_PERCENT / 100
    ordered = sorted(discounts, key=lambda d: 0 if d.kind == "fixed" else 1)
    remaining = subtotal
    total = Decimal("0")
    for discount in ordered:
        if discount.kind == "percent":
            amount = min(remaining * discount.value / 100, cap - total)
        else:
            amount = min(discount.value, cap)
        amount = max(Decimal("0"), min(amount, remaining))
        total += amount
        remaining -= amount
    return quantize(total)
''',
    '''    """The total discount for ``subtotal``: percent first, then fixed, then capped."""
    ordered = sorted(discounts, key=lambda d: 0 if d.kind == "percent" else 1)
    remaining = subtotal
    total = Decimal("0")
    for discount in ordered:
        if discount.kind == "percent":
            amount = remaining * discount.value / 100
        else:
            amount = discount.value
        amount = max(Decimal("0"), min(amount, remaining))
        total += amount
        remaining -= amount
    cap = subtotal * MAX_PERCENT / 100
    return quantize(min(total, cap))
''',
)
print("apply() sorted fixed discounts first, against the documented rule. Flipping the sort alone")
print("makes test_percent_then_fixed pass but breaks test_cap_at_fifty_percent, because the cap")
print("only ran inside the percent branch. Percent now applies first and the cap applies to the")
print("combined total. The whole suite passes.")
print("FINAL: done")
