"""Payment receipts: when an invoice is settled, a receipt is queued for the mailer."""

from __future__ import annotations

from dataclasses import dataclass

from ledger import events
from ledger.money import format_money


@dataclass(frozen=True)
class Receipt:
    invoice: str
    customer: str
    amount: str  # formatted for the customer, e.g. "$58.96"


# Receipts waiting for the mailer, which drains this list every few minutes.
OUTBOX: list[Receipt] = []


@events.on("invoice_settled")
def queue_receipt(invoice) -> None:
    OUTBOX.append(Receipt(invoice.number, invoice.customer, format_money(invoice.total())))
