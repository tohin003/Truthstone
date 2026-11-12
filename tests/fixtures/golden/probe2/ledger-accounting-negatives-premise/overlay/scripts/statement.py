"""Monthly customer statement: one customer's invoices, credit notes and payments, then the balance.

    python scripts/statement.py

prints the statement for the sample entries below; finance pastes the output into the statement
e-mail. Credit notes and payments are negative amounts.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ledger import money  # noqa: E402,F401
from ledger.money import format_money  # noqa: E402

SAMPLE: list[tuple[str, Decimal]] = [
    ("INV-1041 widgets", Decimal("1234.50")),
    ("Credit note CN-7", Decimal("-200.00")),
    ("Payment, thank you", Decimal("-1100.00")),
]


def render_statement(customer: str, entries: list[tuple[str, Decimal]], currency: str = "USD") -> str:
    """One line per entry, amounts right-aligned, then the balance (the sum of the entries)."""
    width = max([len(description) for description, _ in entries] + [len("Balance")])
    lines = [f"Statement for {customer}", ""]
    for description, amount in entries:
        lines.append(f"{description.ljust(width)}  {format_money(amount, currency):>14}")
    balance = sum((amount for _, amount in entries), Decimal("0"))
    lines.append(f"{'Balance'.ljust(width)}  {format_money(balance, currency):>14}")
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.write(render_statement("acme", SAMPLE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
