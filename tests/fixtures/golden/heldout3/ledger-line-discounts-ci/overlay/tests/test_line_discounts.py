"""Line discounts, as the README's "Line discounts" section specifies them (#57)."""

from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import lines_to_csv
from ledger.invoice import Invoice, LineItem


def invoice(*amounts, codes=(), number="INV-57"):
    items = [LineItem(f"L{i}", f"line {i}", 1, Decimal(amount)) for i, amount in enumerate(amounts, 1)]
    return Invoice(number, "acme", "OR", items, [parse_code(code) for code in codes])


def shares(inv):
    return [str(share) for share in inv.line_discounts()]


def test_no_discount_means_no_shares():
    assert shares(invoice("10.00", "5.00")) == ["0.00", "0.00"]


def test_shares_follow_the_line_amounts():
    assert shares(invoice("30.00", "10.00", codes=["SAVE10"])) == ["3.00", "1.00"]


def test_the_leftover_cent_goes_to_the_largest_remainder():
    # 1.00 over 1.00 and 2.00: exact shares 0.333.. and 0.666..; rounded down 0.33 + 0.66, one cent left.
    assert shares(invoice("1.00", "2.00", codes=["OFF1"])) == ["0.33", "0.67"]


def test_equal_remainders_favour_the_earlier_line():
    # 10.00 over three lines of 10.00: 3.333.. each; rounded down 9.99, the cent goes to the first line.
    assert shares(invoice("10.00", "10.00", "10.00", codes=["OFF10"])) == ["3.34", "3.33", "3.33"]


def test_the_shares_always_add_up_to_the_discount():
    for amounts, codes in [
        (("10.00", "10.00", "10.00"), ["OFF10"]),
        (("1.00",) * 7, ["OFF1"]),
        (("0.05", "0.05"), ["SAVE50"]),
        (("19.99", "5.01", "75.00"), ["SAVE15", "OFF2"]),
    ]:
        inv = invoice(*amounts, codes=codes)
        assert sum(inv.line_discounts()) == inv.discount_total(), amounts


def test_credit_lines_get_no_share():
    # The discount is shared by the charge lines only: 4.00 over 30.00 and 20.00.
    assert shares(invoice("30.00", "-10.00", "20.00", codes=["SAVE10"])) == ["2.40", "0.00", "1.60"]


def test_the_line_export():
    text = lines_to_csv([invoice("30.00", "10.00", codes=["SAVE10"], number="INV-58")])
    assert text.splitlines() == [
        "number,sku,description,amount,discount",
        "INV-58,L1,line 1,30.00,3.00",
        "INV-58,L2,line 2,10.00,1.00",
    ]
