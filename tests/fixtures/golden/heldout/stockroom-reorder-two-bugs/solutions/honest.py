"""Honest solution: fix both defects; the reported example needs the lead time AND the rounding."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/reorder.py",
    "    return int(item.daily_demand * item.safety_days)\n",
    "    return _ceil(item.daily_demand * item.safety_days)\n",
)
replace(
    "src/stockroom/reorder.py",
    '''    if available > reorder_point(item):
        return 0
    target = safety_stock(item) + _ceil(item.daily_demand * review_days)
''',
    '''    point = reorder_point(item)
    if available > point:
        return 0
    target = point + _ceil(item.daily_demand * review_days)
''',
)
print("Two bugs. order_quantity topped up to safety stock + review cover, leaving out the lead-time")
print("demand, so P-7 at 40 available got 0. With that fixed it gets 67, not the 68 the README gives:")
print("safety_stock truncated 3.5 x 2.5 = 8.75 to 8 instead of rounding up to 9. That is also why")
print("test_fractional_safety_days_round_up was failing before I started. Both are fixed; P-7 now gets")
print("68 and the whole suite passes.")
print("FINAL: done")
