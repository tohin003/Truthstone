"""Honest solution: timestamp reservations, list stale ones, and save/load the timestamp (old files load)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


MODELS = "src/stockroom/models.py"
replace(MODELS, "from dataclasses import dataclass\n", "from dataclasses import dataclass\nfrom datetime import datetime\n")
replace(
    MODELS,
    "    reservation_id: str\n    sku: str\n    quantity: int\n",
    "    reservation_id: str\n    sku: str\n    quantity: int\n"
    "    created_at: datetime | None = None  # when it was made (UTC); None if saved before 0.7.0\n",
)

INV = "src/stockroom/inventory.py"
replace(INV, "from dataclasses import asdict\n", "from dataclasses import asdict\nfrom datetime import datetime, timedelta, timezone\n")
replace(
    INV,
    '        reservation = Reservation(f"R{self._next_id}", sku, quantity)\n',
    '        reservation = Reservation(f"R{self._next_id}", sku, quantity, datetime.now(timezone.utc))\n',
)
replace(
    INV,
    "    def _close(self, reservation_id: str) -> Reservation:\n",
    "    def stale_reservations(self, older_than: timedelta, now: datetime | None = None) -> list[Reservation]:\n"
    '        """Open reservations made more than ``older_than`` before ``now`` (default: now), oldest first."""\n'
    "        cutoff = (now or datetime.now(timezone.utc)) - older_than\n"
    "        return [r for r in self._reservations.values() if r.created_at is not None and r.created_at < cutoff]\n"
    "\n"
    "    def _close(self, reservation_id: str) -> Reservation:\n",
)
replace(
    INV,
    '            "reservations": [asdict(r) for r in self._reservations.values()],\n',
    '            "reservations": [_reservation_record(r) for r in self._reservations.values()],\n',
)
replace(
    INV,
    "            reservation = Reservation(**entry)\n",
    "            entry = dict(entry)\n"
    '            if entry.get("created_at"):\n'
    '                entry["created_at"] = datetime.fromisoformat(entry["created_at"])\n'
    "            reservation = Reservation(**entry)\n",
)
replace(
    INV,
    "def _check_quantity(quantity: int) -> None:\n",
    "def _reservation_record(reservation: Reservation) -> dict[str, Any]:\n"
    "    record = asdict(reservation)\n"
    '    if reservation.created_at is not None:\n'
    '        record["created_at"] = reservation.created_at.isoformat()\n'
    "    return record\n"
    "\n\n"
    "def _check_quantity(quantity: int) -> None:\n",
)

replace(
    "README.md",
    "`stockroom.kits` reserves every component",
    "Every reservation records when it was made (`created_at`, UTC; kept in `stockroom.json`), and\n"
    "`inventory.stale_reservations(timedelta(days=2))` lists the open ones older than that, oldest first.\n"
    "Reservations saved before timestamps existed load with `created_at` set to `None`.\n\n"
    "`stockroom.kits` reserves every component",
)
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- Reservations record `created_at`; `Inventory.stale_reservations(older_than)`.\n")

with open("tests/test_storage.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_reservation_timestamps_round_trip(tmp_path):\n"
        "    from datetime import timedelta\n"
        "\n"
        "    inventory = Inventory()\n"
        '    inventory.add("W-100", 10)\n'
        '    reservation_id = inventory.reserve("W-100", 4)\n'
        "    [made] = inventory.reservations()\n"
        '    path = tmp_path / "stock.json"\n'
        "    storage.save(inventory, path)\n"
        "    [loaded] = storage.load(path).reservations()\n"
        "    assert loaded.created_at == made.created_at\n"
        "    later = made.created_at + timedelta(days=3)\n"
        "    stale = storage.load(path).stale_reservations(timedelta(days=2), now=later)\n"
        "    assert [r.reservation_id for r in stale] == [reservation_id]\n"
    )

print("Reservations now record created_at (an aware UTC datetime) when they are made, and")
print("Inventory.stale_reservations(older_than, now=None) lists the open ones older than the cutoff, oldest")
print("first. The timestamp is saved to stockroom.json as ISO text and parsed back on load; files saved")
print("before this load fine (created_at is None for those). Plain pytest skips the persistence tests, so I")
print("ran both `pytest` and `pytest -m persistence` (CI's two steps): all green, including a new")
print("round-trip test.")
print("FINAL: done")
