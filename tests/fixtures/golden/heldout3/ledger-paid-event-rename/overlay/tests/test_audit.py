from decimal import Decimal

from ledger import audit
from ledger.invoice import Invoice, LineItem


def invoice(number):
    return Invoice(number, "initech", "OR", [LineItem("G-2", "Gadget", 1, Decimal("25.00"))])


def test_issuing_and_voiding_are_recorded():
    inv = invoice("INV-40")
    inv.issue()
    inv.void()
    assert audit.TRAIL == ["INV-40 invoice_issued", "INV-40 invoice_voided"]


def test_the_trail_keeps_the_order_of_events_across_invoices():
    first, second = invoice("INV-41"), invoice("INV-42")
    first.issue()
    second.issue()
    first.void()
    assert audit.TRAIL == ["INV-41 invoice_issued", "INV-42 invoice_issued", "INV-41 invoice_voided"]
