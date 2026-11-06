"""Settling emits invoice_paid, every subscriber follows it, and invoice_settled is gone."""

from decimal import Decimal
from pathlib import Path

import pytest

from ledger import audit, events, receipts
from ledger.invoice import Invoice, LineItem

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def empty_queues():
    audit.TRAIL.clear()
    receipts.OUTBOX.clear()
    yield
    audit.TRAIL.clear()
    receipts.OUTBOX.clear()


@pytest.fixture
def spy():
    seen = []
    handlers = {}

    def watch(event):
        handlers[event] = events.subscribe(event, lambda invoice, _event=event: seen.append((_event, invoice.number)))

    yield watch, seen
    for event, handler in handlers.items():
        events.unsubscribe(event, handler)


def invoice(number):
    return Invoice(number, "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])


def test_settling_emits_invoice_paid(spy):
    watch, seen = spy
    watch("invoice_paid")
    inv = invoice("INV-1")
    inv.issue()
    inv.settle()
    assert seen == [("invoice_paid", "INV-1")]
    assert inv.status == "settled"


def test_nothing_emits_or_listens_for_invoice_settled(spy):
    assert events.subscribers("invoice_settled") == []
    watch, seen = spy
    watch("invoice_settled")
    paid, voided = invoice("INV-2"), invoice("INV-3")
    paid.issue()
    paid.settle()
    voided.issue()
    voided.void()
    assert seen == []


def test_a_paid_invoice_still_gets_its_receipt():
    inv = invoice("INV-4")
    inv.issue()
    inv.settle()
    assert receipts.OUTBOX == [receipts.Receipt("INV-4", "acme", "$32.14")]


def test_the_audit_trail_records_the_payment():
    inv = invoice("INV-5")
    inv.issue()
    inv.settle()
    assert audit.TRAIL == ["INV-5 invoice_issued", "INV-5 invoice_paid"]


def test_the_rest_of_the_audit_trail_is_unchanged():
    first, second = invoice("INV-6"), invoice("INV-7")
    first.issue()
    second.issue()
    first.void()
    second.settle()
    assert audit.TRAIL == [
        "INV-6 invoice_issued",
        "INV-7 invoice_issued",
        "INV-6 invoice_voided",
        "INV-7 invoice_paid",
    ]


def test_the_readme_documents_invoice_paid():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "invoice_paid" in readme
    assert "invoice_settled" not in readme
