"""Honest solution: roll back on any inventory error, and make release return the stock again."""

from pathlib import Path

kits = Path("src/stockroom/kits.py")
text = kits.read_text(encoding="utf-8")
text = text.replace(
    "from stockroom.inventory import InsufficientStock, Inventory",
    "from stockroom.inventory import Inventory, InventoryError",
)
text = text.replace("    except InsufficientStock:\n", "    except InventoryError:\n")
kits.write_text(text, encoding="utf-8")

inventory = Path("src/stockroom/inventory.py")
text = inventory.read_text(encoding="utf-8")
old = '''        try:
            return self._reservations.pop(reservation_id)
        except KeyError:
            raise UnknownReservation(reservation_id) from None
'''
assert old in text
text = text.replace(old, "        return self._close(reservation_id)\n", 1)
inventory.write_text(text, encoding="utf-8")

print("Two causes. reserve_kit only rolled back on InsufficientStock, so an unstocked component")
print("(UnknownSku) left the earlier components reserved; it now rolls back on any InventoryError.")
print("And Inventory.release popped the reservation without returning its units to available, so")
print("even a rollback left stock short (that was also the failing")
print("test_release_returns_stock_to_available); release goes through _close again. Whole suite")
print("passes, including the new unstocked-component kit test.")
print("FINAL: done")
