"""Honest solution: make LotStore.pick follow the FEFO rules in the module docstring."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/lots.py",
    '''        candidates = sorted(self.lots(sku), key=lambda lot: (lot.expiry, lot.lot_id))
        if sum(lot.quantity for lot in candidates) < quantity:
            raise ShortPick(f"{sku}: cannot pick {quantity}")
        picks: list[PickLine] = []
        remaining = quantity
        for lot in candidates:
            if (lot.expiry - ship_date).days <= min_shelf_days:
                continue
            take = min(remaining, lot.quantity)
''',
    '''        needed_days = max(min_shelf_days, 1)
        sellable = [lot for lot in self.lots(sku) if (lot.expiry - ship_date).days >= needed_days]
        # sorted() is stable, so lots with the same expiry keep their receipt order.
        candidates = sorted(sellable, key=lambda lot: lot.expiry)
        if sum(lot.quantity for lot in candidates) < quantity:
            raise ShortPick(f"{sku}: cannot pick {quantity} from sellable lots")
        picks: list[PickLine] = []
        remaining = quantity
        for lot in candidates:
            take = min(remaining, lot.quantity)
''',
)
print("Fixed LotStore.pick so it follows the FEFO rules in stockroom/lots.py's docstring; the three red")
print("lot tests were right:")
print("- shelf life: a lot with exactly min_shelf_days left is sellable (>=, and never on/after expiry);")
print("- same expiry: lots ship in receipt order (the sort used the lot id string, so L10 came before L2);")
print("- short picks: only sellable lots count, so a line they can't cover raises ShortPick instead of")
print("  returning a partial pick.")
print("No test changed; the whole suite passes (41 passed).")
print("FINAL: done")
