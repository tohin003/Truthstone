from decimal import ROUND_FLOOR, Decimal

import pytest

from ledger.money import allocate

CENT = Decimal("0.01")
AMOUNTS = ["0.00", "0.01", "0.05", "0.99", "1.00", "10.00", "99.99", "100.00", "1234.57"]
WEIGHTS = [[1], [1, 1], [1, 1, 1], [1, 2, 3], [3, 1], [7, 0, 2], [Decimal("0.5"), Decimal("0.25"), Decimal("0.25")]]


@pytest.mark.parametrize("amount", AMOUNTS)
@pytest.mark.parametrize("weights", WEIGHTS)
def test_shares_are_exact_and_within_a_cent_of_their_proportion(amount, weights):
    value = Decimal(amount)
    shares = allocate(value, weights)
    assert len(shares) == len(weights)
    assert sum(shares, Decimal("0")) == value
    total = sum((Decimal(w) for w in weights), Decimal("0"))
    for share, weight in zip(shares, weights):
        assert share == share.quantize(CENT)
        floor = (value * Decimal(weight) / total).quantize(CENT, rounding=ROUND_FLOOR)
        assert floor <= share <= floor + CENT


def test_largest_remainders_get_the_leftover_cents():
    assert allocate(Decimal("1.00"), [1, 1, 1]) == [Decimal("0.34"), Decimal("0.33"), Decimal("0.33")]
    # exact 0.1666..., 0.3333..., 0.5: rounded down 0.16 + 0.33 + 0.50, the first lost most.
    assert allocate(Decimal("1.00"), [1, 2, 3]) == [Decimal("0.17"), Decimal("0.33"), Decimal("0.50")]
    # exact 0.0666... and 0.0333...: the first lost more.
    assert allocate(Decimal("0.10"), [2, 1]) == [Decimal("0.07"), Decimal("0.03")]


def test_ties_go_to_earlier_shares():
    assert allocate(Decimal("0.05"), [1, 1]) == [Decimal("0.03"), Decimal("0.02")]
    assert allocate(Decimal("0.04"), [1, 1, 1]) == [Decimal("0.02"), Decimal("0.01"), Decimal("0.01")]


def test_a_zero_weight_gets_nothing():
    assert allocate(Decimal("5.00"), [0, 1]) == [Decimal("0.00"), Decimal("5.00")]


def test_invalid_input_is_rejected():
    for amount, weights in [(Decimal("-0.01"), [1]), (Decimal("1.00"), [0, 0]), (Decimal("1.00"), [1, -1])]:
        with pytest.raises(ValueError):
            allocate(amount, weights)
