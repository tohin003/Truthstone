from decimal import Decimal

import pytest

from ledger import events
from ledger.invoice import Invoice, InvoiceStateError, LineItem


def invoice(number="INV-20"):
    return Invoice(number, "acme", "CA", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])


def test_an_invoice_is_issued_then_settled():
    inv = invoice()
    assert inv.status == "draft"
    inv.issue()
    assert inv.status == "issued"
    inv.settle()
    assert inv.status == "settled"


def test_an_issued_invoice_can_be_voided():
    inv = invoice()
    inv.issue()
    inv.void()
    assert inv.status == "voided"


@pytest.mark.parametrize("steps", [["settle"], ["void"], ["issue", "issue"], ["issue", "void", "settle"]])
def test_steps_out_of_order_are_refused(steps):
    inv = invoice()
    for step in steps[:-1]:
        getattr(inv, step)()
    with pytest.raises(InvoiceStateError):
        getattr(inv, steps[-1])()


def test_settling_emits_invoice_settled():
    seen = []
    handler = events.subscribe("invoice_settled", lambda invoice: seen.append(invoice.number))
    try:
        inv = invoice("INV-21")
        inv.issue()
        assert seen == []
        inv.settle()
    finally:
        events.unsubscribe("invoice_settled", handler)
    assert seen == ["INV-21"]
