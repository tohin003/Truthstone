"""The documented discount rules: percent first, then fixed, the total capped at 50%."""

from decimal import Decimal

from ledger.discounts import apply, parse_code


def codes(*names):
    return [parse_code(name) for name in names]


def test_percent_applies_before_fixed_whatever_the_order_given():
    assert apply(Decimal("100.00"), codes("OFF5", "SAVE10")) == Decimal("15.00")
    assert apply(Decimal("100.00"), codes("SAVE10", "OFF5")) == Decimal("15.00")


def test_percent_and_fixed_together_are_capped():
    assert apply(Decimal("20.00"), codes("SAVE40", "OFF5")) == Decimal("10.00")
    assert apply(Decimal("20.00"), codes("OFF5", "SAVE40")) == Decimal("10.00")
    assert apply(Decimal("30.00"), codes("SAVE30", "OFF10")) == Decimal("15.00")


def test_single_discounts_unchanged():
    assert apply(Decimal("80.00"), codes("SAVE10")) == Decimal("8.00")
    assert apply(Decimal("3.00"), codes("OFF5")) == Decimal("1.50")
    assert apply(Decimal("100.00"), codes("SAVE60")) == Decimal("50.00")
    assert apply(Decimal("20.00"), []) == Decimal("0.00")
