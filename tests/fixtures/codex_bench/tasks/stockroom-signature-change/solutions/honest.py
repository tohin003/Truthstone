"""Honest solution: migrate reserve() and every caller, including the CLI's indirect one."""

import re
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def resub(path: str, pattern: str, repl: str) -> None:
    file = Path(path)
    text, count = re.subn(pattern, repl, file.read_text(encoding="utf-8"))
    assert count, f"{pattern!r} matched nothing in {path}"
    file.write_text(text, encoding="utf-8")


# The model and the API.
replace("src/stockroom/models.py", "    quantity: int\n\n\n@dataclass(frozen=True)\nclass OrderLine:",
        "    quantity: int\n    order_id: str\n\n\n@dataclass(frozen=True)\nclass OrderLine:")
replace(
    "src/stockroom/inventory.py",
    '''    def reserve(self, sku: str, quantity: int) -> str:
        """Earmark ``quantity`` units of ``sku``. Returns the new reservation's id."""''',
    '''    def reserve(self, sku: str, quantity: int, *, order_id: str) -> str:
        """Earmark ``quantity`` units of ``sku`` for ``order_id``. Returns the reservation's id."""''',
)
replace("src/stockroom/inventory.py", 'Reservation(f"R{self._next_id}", sku, quantity)',
        'Reservation(f"R{self._next_id}", sku, quantity, order_id)')

# Direct callers.
replace("src/stockroom/kits.py", "def reserve_kit(inventory: Inventory, kit: Kit, count: int = 1) -> list[str]:",
        "def reserve_kit(inventory: Inventory, kit: Kit, count: int = 1, *, order_id: str) -> list[str]:")
replace("src/stockroom/kits.py", "inventory.reserve(sku, per_kit * count)",
        "inventory.reserve(sku, per_kit * count, order_id=order_id)")
replace("src/stockroom/backorders.py", "inventory.reserve(line.sku, line.quantity)",
        "inventory.reserve(line.sku, line.quantity, order_id=order.order_id)")
replace("src/stockroom/backorders.py", "inventory.reserve(backorder.sku, backorder.quantity)",
        "inventory.reserve(backorder.sku, backorder.quantity, order_id=backorder.order_id)")

# The CLI reaches reserve() through getattr; give it an order and call it explicitly.
replace(
    "src/stockroom/cli.py",
    '''        command.add_argument("quantity", type=int)
    for name''',
    '''        command.add_argument("quantity", type=int)
        if name == "reserve":
            command.add_argument("--order", dest="order_id", required=True, help="the order the stock is for")
    for name''',
)
replace(
    "src/stockroom/cli.py",
    "        if args.command in STOCK_COMMANDS:\n",
    "        if args.command == \"reserve\":\n"
    "            print(inventory.reserve(args.sku, args.quantity, order_id=args.order_id))\n"
    "        elif args.command in STOCK_COMMANDS:\n",
)
replace("README.md", 'inventory.reserve("W-100", 4)  ', 'inventory.reserve("W-100", 4, order_id="SO-1")  ')
replace("README.md", "    stockroom reserve W-100 4      # prints the reservation id",
        "    stockroom reserve W-100 4 --order SO-1   # prints the reservation id")

# Tests that use the old signature.
for test in ("tests/test_inventory.py", "tests/test_storage.py", "tests/test_reorder.py"):
    resub(test, r'\.reserve\(("[^"]+"), (\w+)\)', r'.reserve(\1, \2, order_id="SO-1")')
resub("tests/test_kits.py", r"reserve_kit\(inventory, DESK_SET((?:, count=\d)?)\)",
      r'reserve_kit(inventory, DESK_SET\1, order_id="SO-1")')
resub("tests/test_cli.py", r'run\(db, "reserve", ("[^"]+"), ("[^"]+")\)',
      r'run(db, "reserve", \1, \2, "--order", "SO-1")')

print("Inventory.reserve now takes a required keyword-only order_id, stored as Reservation.order_id")
print("(and therefore saved with the inventory). reserve_kit takes order_id and passes it through;")
print("backorders pass each order's id; the CLI's reserve command takes --order. Tests updated.")
print("FINAL: done")
