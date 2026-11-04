"""Invoice.installments(n): n amounts that add up exactly to the total, extra cents first."""

from decimal import Decimal

import pytest

from ledger.invoice import Invoice, LineItem


def invoice(price, region="OR", quantity=1):
    return Invoice("INV-1", "acme", region, [LineItem("W-1", "Widget", quantity, Decimal(price))])


def test_an_even_split():
    assert invoice("100.00").installments(4) == [Decimal("25.00")] * 4


def test_the_extra_cents_go_to_the_earlier_payments():
    assert invoice("100.00").installments(3) == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert invoice("100.01").installments(3) == [Decimal("33.34"), Decimal("33.34"), Decimal("33.33")]


def test_the_total_includes_tax():
    taxed = invoice("10.00", region="CA", quantity=3)  # 30.00 + 2.18 tax = 32.18
    assert taxed.installments(4) == [Decimal("8.05"), Decimal("8.05"), Decimal("8.04"), Decimal("8.04")]


def test_one_installment_is_the_whole_total():
    single = invoice("58.96", region="CA")
    assert single.installments(1) == [single.total()]


def test_more_installments_than_cents():
    assert invoice("0.05").installments(7) == [Decimal("0.01")] * 5 + [Decimal("0.00")] * 2


def test_payments_always_add_up_to_the_total():
    for price in ("0.01", "1.00", "19.99", "100.00", "123.45"):
        for region in ("CA", "OR"):
            whole = invoice(price, region)
            for n in range(1, 13):
                parts = whole.installments(n)
                assert len(parts) == n
                assert sum(parts, Decimal("0")) == whole.total()
                assert max(parts) - min(parts) <= Decimal("0.01")
                assert parts == sorted(parts, reverse=True)
                assert all(part == part.quantize(Decimal("0.01")) for part in parts)


@pytest.mark.parametrize("n", [0, -1, -12])
def test_n_must_be_at_least_one(n):
    with pytest.raises(ValueError):
        invoice("100.00").installments(n)
