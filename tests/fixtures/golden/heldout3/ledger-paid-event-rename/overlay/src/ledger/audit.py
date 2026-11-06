"""The audit trail: one line per invoice lifecycle step, which finance checks at month end.

Every step after the draft is recorded, as ``"<invoice number> <event>"``. The trail must not
miss a step: the month-end reconciliation flags any invoice whose trail is incomplete.
"""

from __future__ import annotations

from ledger import events
from ledger.invoice import LIFECYCLE

# The trail, oldest first; the nightly job appends it to the audit store and clears it.
TRAIL: list[str] = []


def _recorder(event: str):
    def record(invoice) -> None:
        TRAIL.append(f"{invoice.number} {event}")

    return record


# One subscription per lifecycle step: each step's event is named after the status it leads to.
for _status in LIFECYCLE[1:]:
    events.subscribe(f"invoice_{_status}", _recorder(f"invoice_{_status}"))
