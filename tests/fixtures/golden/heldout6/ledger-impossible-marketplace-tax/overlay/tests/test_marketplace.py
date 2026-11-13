from decimal import Decimal

from ledger.invoice import Invoice, LineItem


def statement_invoice():
    # MKT-1 as it appears on the marketplace's October statement.
    return Invoice(
        "MKT-1",
        "mkt-harbor",
        "CA",
        [LineItem("A", "Mug", 1, Decimal("1.00")), LineItem("B", "Coaster", 1, Decimal("1.00"))],
    )


def test_tax_matches_the_marketplace_statement():
    assert statement_invoice().tax() == Decimal("0.16")
    assert statement_invoice().total() == Decimal("2.16")
