from decimal import Decimal

import pytest

from ledger.discounts import Discount, InvalidCode, apply, parse_code


def test_parse_codes():
    assert parse_code("save10") == Discount("percent", Decimal("10"), "SAVE10")
    assert parse_code("OFF5") == Discount("fixed", Decimal("5"), "OFF5")


def test_parse_rejects_unknown_codes():
    with pytest.raises(InvalidCode):
        parse_code("FREE")


def test_percent_codes_above_100_are_invalid():
    for code in ("SAVE101", "SAVE150", "save999"):
        with pytest.raises(InvalidCode):
            parse_code(code)
    assert parse_code("SAVE100") == Discount("percent", Decimal("100"), "SAVE100")


def test_percent_discount():
    assert apply(Decimal("80.00"), [parse_code("SAVE10")]) == Decimal("8.00")


def test_percent_then_fixed():
    # 10% of 100 = 10, then 5 off: 15 in total.
    assert apply(Decimal("100.00"), [parse_code("OFF5"), parse_code("SAVE10")]) == Decimal("15.00")


def test_fixed_never_goes_negative():
    assert apply(Decimal("3.00"), [parse_code("OFF5")]) == Decimal("1.50")


def test_cap_at_fifty_percent():
    # 40% of 20 = 8, then 5 off = 13, capped at half of 20.
    assert apply(Decimal("20.00"), [parse_code("SAVE40"), parse_code("OFF5")]) == Decimal("10.00")


def test_no_discounts():
    assert apply(Decimal("20.00"), []) == Decimal("0.00")
