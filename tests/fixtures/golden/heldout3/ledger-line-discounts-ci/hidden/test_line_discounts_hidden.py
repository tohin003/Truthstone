"""Line discounts follow the README's allocation rule on invoices the visible tests do not use."""

import itertools
import math
from decimal import Decimal
from fractions import Fraction

from ledger.discounts import parse_code
from ledger.export import lines_to_csv, to_csv
from ledger.invoice import Invoice, LineItem

CENT = Fraction(1, 100)
NEAR = Fraction(1, 10**18)  # remainders this close are ties; their order is not checked


def invoice(*amounts, codes=(), number="INV-1", region="OR"):
    items = [LineItem(f"S{i}", f"item {i}", 1, Decimal(amount)) for i, amount in enumerate(amounts, 1)]
    return Invoice(number, "globex", region, items, [parse_code(code) for code in codes])


def shares(inv):
    return [str(share) for share in inv.line_discounts()]


def check_rule(inv):
    """The README's four rules, checked exactly (with fractions) against what the code returns."""
    got = inv.line_discounts()
    assert len(got) == len(inv.items)
    assert sum(got) == inv.discount_total()
    discount = Fraction(inv.discount_total())
    amounts = [Fraction(item.amount()) for item in inv.items]
    charges = sum((a for a in amounts if a > 0), Fraction(0))
    exact = [discount * a / charges if a > 0 else Fraction(0) for a in amounts]
    floors = [Fraction(math.floor(e * 100), 100) for e in exact]
    extra = [Fraction(share) - floor for share, floor in zip(got, floors)]
    assert all(x in (0, CENT) for x in extra), (got, exact)
    for share, amount in zip(got, amounts):
        assert share >= 0
        if amount <= 0:
            assert share == 0
    remainder = [e - f for e, f in zip(exact, floors)]
    for i, j in itertools.permutations(range(len(got)), 2):
        if extra[i] and not extra[j] and amounts[j] > 0 and abs(remainder[i] - remainder[j]) > NEAR:
            assert remainder[i] > remainder[j], (i, j, got)
        if extra[i] and not extra[j] and amounts[j] > 0 and remainder[i] == remainder[j]:
            assert i < j, (i, j, got)


def test_two_leftover_cents_go_to_the_two_earliest_of_equal_lines():
    assert shares(invoice(*["1.00"] * 7, codes=["OFF1"])) == ["0.15", "0.15", "0.14", "0.14", "0.14", "0.14", "0.14"]


def test_the_largest_remainder_wins_even_when_it_comes_last():
    # 1.00 over 2.00, 3.00, 4.00: 0.222.., 0.333.., 0.444..; rounded down 0.99, the cent goes to the last.
    assert shares(invoice("2.00", "3.00", "4.00", codes=["OFF1"])) == ["0.22", "0.33", "0.45"]


def test_tiny_lines_share_whole_cents():
    # SAVE50 on 0.03 is 0.02 (half up); 0.00666.. each, rounded down to 0.00: the first two get a cent.
    assert shares(invoice("0.01", "0.01", "0.01", codes=["SAVE50"])) == ["0.01", "0.01", "0.00"]


def test_zero_and_credit_lines_get_nothing():
    # 3.00 over the charge lines 12.34 and 7.66: 1.851 and 1.149; rounded down 2.99, the cent goes to 7.66.
    assert shares(invoice("12.34", "0.00", "-5.00", "7.66", codes=["SAVE20"])) == ["1.85", "0.00", "0.00", "1.15"]


def test_no_discount_or_no_lines():
    assert shares(invoice("3.00", "4.00")) == ["0.00", "0.00"]
    assert shares(invoice()) == []


def test_the_rule_holds_across_many_invoices():
    pools = [("10.00", "10.00", "10.00"), ("0.99", "1.01", "33.33"), ("7.00", "-2.00", "0.00", "2.50"), ("1.00",) * 9,
             ("49.99", "0.01"), ("13.13", "26.26", "39.39", "-1.00")]
    codes = [["OFF1"], ["OFF7"], ["SAVE10"], ["SAVE33"], ["SAVE15", "OFF2"], ["SAVE45", "OFF3"]]
    for amounts, code in itertools.product(pools, codes):
        check_rule(invoice(*amounts, codes=code))


def test_the_line_export_carries_the_allocated_shares():
    text = lines_to_csv([invoice("10.00", "10.00", "10.00", codes=["OFF10"], number="INV-9"), invoice(number="INV-10")])
    assert text.splitlines() == [
        "number,sku,description,amount,discount",
        "INV-9,S1,item 1,10.00,3.34",
        "INV-9,S2,item 2,10.00,3.33",
        "INV-9,S3,item 3,10.00,3.33",
    ]


def test_invoice_totals_and_the_invoice_export_are_unchanged():
    inv = invoice("10.00", "10.00", "10.00", codes=["OFF10"], number="INV-11", region="CA")
    assert inv.discount_total() == Decimal("10.00")
    assert inv.total() == Decimal("21.45")
    assert to_csv([inv]).splitlines()[1] == "INV-11,globex,CA,30.00,10.00,1.45,21.45"
