from decimal import Decimal

from ledger.invoice import Invoice, LineItem
from ledger.statement import render


def test_statement_lists_the_amounts():
    invoice = Invoice("INV-3", "initech", "NY", [LineItem("W-1", "Widget", 4, Decimal("12.50"))])
    assert render(invoice) == (
        "Statement for initech\n"
        "Invoice INV-3\n"
        "  Subtotal        $50.00\n"
        "  Tax              $2.00\n"
        "  Total           $52.00\n"
    )


def test_statement_in_euros():
    invoice = Invoice("INV-4", "umbrella", "OR", [LineItem("G-2", "Gadget", 1, Decimal("1250.00"))])
    assert render(invoice, "EUR").splitlines()[-1] == "  Total        €1,250.00"
