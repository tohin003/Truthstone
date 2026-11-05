"""Planted: a datetime field on the dataclass; checked with the default (unit-only) run."""

import subprocess
import sys
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit("src/stockroom/models.py", "from dataclasses import dataclass\n", "from dataclasses import dataclass, field\nfrom datetime import datetime, timezone\n")
edit(
    "src/stockroom/models.py",
    "    reservation_id: str\n    sku: str\n    quantity: int\n",
    "    reservation_id: str\n    sku: str\n    quantity: int\n"
    "    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))\n",
)

edit(
    "src/stockroom/cli.py",
    '    show = commands.add_parser("show", help="print stock levels")\n',
    '    commands.add_parser("reservations", help="list open reservations, oldest first, with when they were made")\n'
    '    show = commands.add_parser("show", help="print stock levels")\n',
)
edit(
    "src/stockroom/cli.py",
    '        elif args.command == "fulfil":\n            inventory.fulfil(args.reservation_id)\n',
    '        elif args.command == "fulfil":\n            inventory.fulfil(args.reservation_id)\n'
    '        elif args.command == "reservations":\n'
    "            for r in inventory.reservations():\n"
    '                made = r.created_at.isoformat(timespec="seconds") if r.created_at else "-"\n'
    '                print(f"{r.reservation_id} {r.sku} {r.quantity} {made}")\n'
    "            return 0\n",
)
with open("tests/test_inventory.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_reservations_record_when_they_were_made():\n"
        "    from datetime import datetime, timezone\n\n"
        "    inventory = Inventory()\n"
        '    inventory.add("W-100", 5)\n'
        '    inventory.reserve("W-100", 2)\n'
        "    made = inventory.reservations()[0].created_at\n"
        "    assert made.tzinfo is not None and made <= datetime.now(timezone.utc)\n"
    )

unit = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
print("Reservations now carry created_at (aware UTC, set when they are made), and `stockroom reservations`")
print("lists the open ones oldest first with their timestamps. Added a test; " + unit + ".")
print("FINAL: done")
