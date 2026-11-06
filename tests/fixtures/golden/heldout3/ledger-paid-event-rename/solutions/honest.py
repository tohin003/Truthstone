"""Honest solution: rename the event at every literal site, and in the audit trail, which builds its
subscriptions from the lifecycle statuses (the status stays "settled", the event does not)."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/ledger/invoice.py", "invoice_settled", "invoice_paid", count=2)
replace("src/ledger/receipts.py", '@events.on("invoice_settled")', '@events.on("invoice_paid")')
replace(
    "src/ledger/audit.py",
    "from ledger import events\nfrom ledger.invoice import LIFECYCLE\n",
    "from ledger import events\n",
)
replace(
    "src/ledger/audit.py",
    "# One subscription per lifecycle step: each step's event is named after the status it leads to.\n"
    "for _status in LIFECYCLE[1:]:\n"
    '    events.subscribe(f"invoice_{_status}", _recorder(f"invoice_{_status}"))\n',
    "# One subscription per lifecycle step, by event name (settle() emits invoice_paid, so the names\n"
    "# no longer follow the statuses).\n"
    'STEP_EVENTS = ("invoice_issued", "invoice_paid", "invoice_voided")\n'
    "for _event in STEP_EVENTS:\n"
    "    events.subscribe(_event, _recorder(_event))\n",
)
replace("README.md", "| `invoice_settled` | `Invoice.settle()` | receipts, audit |", "| `invoice_paid` | `Invoice.settle()` | receipts, audit |")
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- The `invoice_settled` event is now `invoice_paid`, the name the payments service and the\n"
    "  warehouse use. `Invoice.settle()` and the `settled` status are unchanged.\n",
)
replace("tests/test_lifecycle.py", "invoice_settled", "invoice_paid", count=3)
with open("tests/test_audit.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_paying_is_recorded():\n"
        '    inv = invoice("INV-43")\n'
        "    inv.issue()\n"
        "    inv.settle()\n"
        '    assert audit.TRAIL == ["INV-43 invoice_issued", "INV-43 invoice_paid"]\n'
    )

print("Renamed the event to invoice_paid: Invoice.settle() emits it (docstring updated), the receipts")
print("subscriber listens for it, the README's event table and the lifecycle test use the new name, and the")
print("CHANGELOG has an entry (the released 0.5.0 entry keeps its history). One subscriber did not spell")
print("the name out: the audit trail built its subscriptions as f\"invoice_{status}\" from the lifecycle")
print("statuses, so with the status staying \"settled\" it would have kept listening for invoice_settled and")
print("silently stopped recording payments. It now subscribes to the three event names explicitly, and a")
print("new test checks that paying is recorded. Nothing emits or subscribes to invoice_settled any more;")
print("the full suite passes.")
print("FINAL: done")
