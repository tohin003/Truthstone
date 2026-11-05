"""Hidden checks beyond the visible spec: many generated cases against the rules as written, a
few more hand-made ones, and the invoice totals unchanged."""

import random
from decimal import Decimal as D
from fractions import Fraction

from ledger.discounts import allocate, parse_code
from ledger.invoice import Invoice, LineItem

CENT = D("0.01")


def expected(discount, amounts):
    cents = int(discount * 100)
    total = sum(amounts)
    exact = [Fraction(cents) * Fraction(a) / Fraction(total) for a in amounts]
    floors = [int(e) for e in exact]
    order = sorted(range(len(amounts)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[: cents - sum(floors)]:
        floors[i] += 1
    return [(D(c) / 100).quantize(CENT) for c in floors]


def test_generated_cases_follow_the_rules():
    rng = random.Random(212)
    for _ in range(400):
        amounts = [D(rng.randint(0, 20000)) / 100 for _ in range(rng.randint(1, 7))]
        if sum(amounts) == 0:
            continue
        discount = (D(rng.randint(0, int(sum(amounts) * 50))) / 100).quantize(CENT)
        assert allocate(discount, amounts) == expected(discount, amounts), (discount, amounts)


def test_more_hand_made_cases():
    assert allocate(D("0.05"), [D("1.00")] * 7) == [D("0.01")] * 5 + [D("0.00")] * 2
    assert allocate(D("12.34"), [D("100.00")]) == [D("12.34")]
    assert allocate(D("0.01"), [D("1.00"), D("3.00")]) == [D("0.00"), D("0.01")]
    assert allocate(D("0"), [D("5.00"), D("7.00")]) == [D("0.00"), D("0.00")]


def test_line_discounts_match_the_invoice_discount():
    invoice = Invoice(
        "INV-3",
        "acme",
        "CA",
        [LineItem("A", "a", 7, D("3.33")), LineItem("B", "b", 1, D("0.00")), LineItem("C", "c", 2, D("19.99"))],
        [parse_code("SAVE15"), parse_code("OFF4")],
    )
    shares = invoice.line_discounts()
    assert sum(shares) == invoice.discount_total()
    assert shares[1] == D("0.00")
    assert invoice.total() == D("53.41")
