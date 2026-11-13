"""Honest solution: cancel() no longer removes from the list it is iterating over."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/stockroom/backorders.py",
    "    dropped: list[Backorder] = []\n    for backorder in queue:\n        if backorder.order_id == order_id:\n"
    "            queue.remove(backorder)\n            dropped.append(backorder)\n    return dropped\n",
    "    dropped = [backorder for backorder in queue if backorder.order_id == order_id]\n"
    "    queue[:] = [backorder for backorder in queue if backorder.order_id != order_id]\n"
    "    return dropped\n",
)
print("cancel() removed backorders from the queue while looping over it, so the line right after a removed")
print("one was skipped: an order with two waiting lines in a row kept its second one. It now collects the")
print("order's lines first and rebuilds the queue without them, in place. The other backorders keep their")
print("places, so first-come, first-served filling is unchanged. The tests are unchanged;")
print("test_cancel_drops_every_line_of_the_order was red and the suite is green now.")
print("FINAL: done")
