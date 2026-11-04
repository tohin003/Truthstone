from datetime import date
from decimal import Decimal

import pytest

from ledger.dunning import reminder
from ledger.invoice import Invoice, LineItem


def invoice():
    return Invoice(
        "INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))], issued_on=date(2026, 11, 3)
    )


def test_second_reminder():
    assert reminder(invoice(), today=date(2026, 12, 4), level=2) == (
        "Second reminder, 04/12/2026\n"
        "\n"
        "Dear globex,\n"
        "\n"
        "our invoice INV-9 of 03/11/2026 for $20.80 is still unpaid.\n"
    )


def test_first_reminder_is_the_default():
    assert reminder(invoice(), today=date(2026, 12, 4)).startswith("Payment reminder, 04/12/2026\n")


def test_unknown_level():
    with pytest.raises(ValueError):
        reminder(invoice(), today=date(2026, 12, 4), level=4)
