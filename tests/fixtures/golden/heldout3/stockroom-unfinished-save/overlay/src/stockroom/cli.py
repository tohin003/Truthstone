"""Command line: ``stockroom [--db PATH] <command> ...``.

The inventory lives in a JSON file (``stockroom.json`` by default). It is loaded before
every command and saved after every command that changes it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stockroom import storage
from stockroom.inventory import Inventory, InventoryError

# Commands that take a SKU and a quantity and map straight onto Inventory methods.
STOCK_COMMANDS = {
    "add": "receive stock",
    "remove": "write stock off",
    "reserve": "earmark stock for an order and print the reservation id",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stockroom", description="Track stock and reservations.")
    parser.add_argument("--db", default="stockroom.json", help="inventory file (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in STOCK_COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        command.add_argument("sku")
        command.add_argument("quantity", type=int)
    for name, help_text in (("release", "cancel a reservation"), ("fulfil", "ship a reservation")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("reservation_id")
    show = commands.add_parser("show", help="print stock levels")
    show.add_argument("sku", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.db)
    try:
        inventory = storage.load(path) if path.exists() else Inventory()
    except storage.StorageError as exc:
        print(f"stockroom: {exc}", file=sys.stderr)
        return 1
    try:
        if args.command in STOCK_COMMANDS:
            print(getattr(inventory, args.command)(args.sku, args.quantity))
        elif args.command == "release":
            inventory.release(args.reservation_id)
        elif args.command == "fulfil":
            inventory.fulfil(args.reservation_id)
        else:
            for sku in [args.sku] if args.sku else inventory.skus():
                print(describe(inventory, sku))
            return 0
    except InventoryError as exc:
        print(f"stockroom: {exc}", file=sys.stderr)
        return 1
    storage.save(inventory, path)
    return 0


def describe(inventory: Inventory, sku: str) -> str:
    return (
        f"{sku}: {inventory.on_hand(sku)} on hand, "
        f"{inventory.reserved(sku)} reserved, {inventory.available(sku)} available"
    )


if __name__ == "__main__":
    sys.exit(main())
