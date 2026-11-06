from decimal import Decimal

from ledger import receipts
from ledger.invoice import Invoice, LineItem


def invoice(number):
    return Invoice(number, "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])


def test_settling_queues_a_receipt():
    inv = invoice("INV-30")
    inv.issue()
    assert receipts.OUTBOX == []
    inv.settle()
    assert receipts.OUTBOX == [receipts.Receipt("INV-30", "globex", "$20.80")]


def test_voided_invoices_get_no_receipt():
    inv = invoice("INV-31")
    inv.issue()
    inv.void()
    assert receipts.OUTBOX == []
