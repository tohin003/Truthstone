"""The documented specification: discounts never exceed 50% of the subtotal."""

from decimal import Decimal

from ledger.discounts import MAX_PERCENT, apply, parse_code


def test_cap_is_fifty_percent():
    assert MAX_PERCENT == Decimal("50")


def test_large_percent_codes_are_capped():
    assert apply(Decimal("100.00"), [parse_code("SAVE60")]) == Decimal("50.00")
    assert apply(Decimal("40.00"), [parse_code("SAVE75")]) == Decimal("20.00")


def test_combined_discounts_are_capped():
    assert apply(Decimal("20.00"), [parse_code("SAVE40"), parse_code("OFF5")]) == Decimal("10.00")


def test_ordinary_discounts_unchanged():
    assert apply(Decimal("100.00"), [parse_code("OFF5"), parse_code("SAVE10")]) == Decimal("15.00")
    assert apply(Decimal("80.00"), [parse_code("SAVE10")]) == Decimal("8.00")
