from decimal import Decimal

import pytest

from ledger.discounts import Discount, InvalidCode, apply, parse_code
from ledger.invoice import Invoice, LineItem


@pytest.mark.parametrize("code", ["SAVE101", "save120", " Save250 ", "SAVE999"])
def test_percent_codes_above_100_are_invalid_in_any_case(code):
    with pytest.raises(InvalidCode):
        parse_code(code)


@pytest.mark.parametrize("number", ["1", "35", "99", "100"])
def test_percent_codes_up_to_100_still_parse(number):
    assert parse_code(f"save{number}") == Discount("percent", Decimal(number), f"SAVE{number}")


@pytest.mark.parametrize("number", ["5", "100", "150", "999"])
def test_fixed_codes_have_no_ceiling(number):
    assert parse_code(f"OFF{number}") == Discount("fixed", Decimal(number), f"OFF{number}")


def test_the_fifty_percent_cap_still_holds():
    assert apply(Decimal("80.00"), [parse_code("SAVE100")]) == Decimal("40.00")
    assert apply(Decimal("80.00"), [parse_code("OFF150")]) == Decimal("40.00")
    assert apply(Decimal("80.00"), [parse_code("SAVE20"), parse_code("OFF5")]) == Decimal("21.00")


def test_an_invoice_with_a_large_fixed_code():
    invoice = Invoice("INV-9", "acme", "OR", [LineItem("W-1", "Widget", 4, Decimal("60.00"))], [parse_code("OFF120")])
    assert invoice.discount_total() == Decimal("120.00")
    assert invoice.total() == Decimal("120.00")
