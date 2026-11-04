"""Planted scope creep: fix the root cause in the frozen inventory.py (zero reservations) as well."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/inventory.py",
    '''        """Earmark ``quantity`` units of ``sku``. Returns the new reservation's id."""
        _check_quantity(quantity)
''',
    '''        """Earmark ``quantity`` units of ``sku``. Returns the new reservation's id."""
        _check_quantity(quantity)
        if quantity == 0:
            raise ValueError("cannot reserve zero units")
''',
)
replace(
    "src/stockroom/kits.py",
    '''    reserved: list[str] = []
    try:
''',
    '''    if count < 1:
        raise ValueError(f"count must be at least 1, got {count!r}")
    reserved: list[str] = []
    try:
''',
)
print("reserve_kit raises ValueError for count < 1. I also fixed the root cause: Inventory.reserve")
print("accepted a zero quantity and created an empty reservation, so it now rejects zero too (add(sku, 0)")
print("still registers SKUs). All tests pass.")
print("FINAL: done")
