import re
from pathlib import Path

from stockroom.backorders import Backorder, fill, promise
from stockroom.inventory import Inventory
from stockroom.models import Order, OrderLine

README = Path("README.md")


def backorders_section():
    text = README.read_text(encoding="utf-8")
    match = re.search(r"^(#{2,3})\s*Backorders\b.*$", text, re.MULTILINE | re.IGNORECASE)
    assert match, "the README has no Backorders section"
    level = len(match.group(1))
    rest = text[match.end():]
    end = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def test_the_section_explains_promise_and_fill():
    section = backorders_section()
    assert "promise" in section
    assert "fill" in section


def test_the_section_states_first_come_first_served():
    section = backorders_section().lower()
    assert re.search(r"first[- ]come,?[\s-]*first[- ]served", section)


def test_the_section_says_new_orders_queue_behind_waiting_backorders():
    section = backorders_section().lower()
    assert "queue" in section or "behind" in section


def test_backorder_behaviour_is_unchanged():
    inventory = Inventory()
    inventory.add("G-200", 1)
    queue = [Backorder("SO-1", "G-200", 2)]
    promise(inventory, Order("SO-2", (OrderLine("G-200", 1),)), queue)
    assert [b.order_id for b in queue] == ["SO-1", "SO-2"]
    assert fill(inventory, queue) == []
    inventory.add("G-200", 2)
    assert [b.order_id for b, _ in fill(inventory, queue)] == ["SO-1", "SO-2"]
