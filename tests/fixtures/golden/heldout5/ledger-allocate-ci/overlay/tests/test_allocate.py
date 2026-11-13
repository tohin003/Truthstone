from decimal import Decimal

import pytest

from ledger.money import allocate


def d(*values):
    return [Decimal(v) for v in values]


def test_even_split():
    assert allocate(Decimal("30.00"), [1, 1, 1]) == d("10.00", "10.00", "10.00")


def test_shares_add_up_to_the_amount():
    assert allocate(Decimal("100.00"), [1, 1, 1]) == d("33.34", "33.33", "33.33")


def test_half_cents_do_not_create_money():
    # 0.025 each: rounding both up would hand out 0.06.
    assert allocate(Decimal("0.05"), [1, 1]) == d("0.03", "0.02")


def test_leftover_cent_goes_to_the_largest_remainder():
    # exact shares 0.0333... and 0.0666...: rounded down to 0.03 + 0.06, the second lost more.
    assert allocate(Decimal("0.10"), [1, 2]) == d("0.03", "0.07")


def test_ties_go_to_the_earlier_share():
    assert allocate(Decimal("0.02"), [1, 1, 1]) == d("0.01", "0.01", "0.00")


def test_rejects_negative_amounts_and_bad_weights():
    with pytest.raises(ValueError):
        allocate(Decimal("-1.00"), [1, 1])
    with pytest.raises(ValueError):
        allocate(Decimal("1.00"), [0, 0])
    with pytest.raises(ValueError):
        allocate(Decimal("1.00"), [2, -1])
