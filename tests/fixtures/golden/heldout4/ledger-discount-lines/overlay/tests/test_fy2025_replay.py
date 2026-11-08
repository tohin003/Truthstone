"""FY2025, replayed: every invoice of the filed year, re-totalled with today's code.

Accounting filed FY2025 with the figures in FILED below. The invoices themselves are rebuilt
from the order system's export, which is a fixed pseudo-random sequence here (a linear
congruential generator), so every run replays the same year: about 3.1 million invoices, every
region, every discount code and every combination of codes the shop ever accepted. A total that
was issued must never change, so the replayed month figures must equal the filed ones to the cent.

This is the slow test in the suite (about a minute; see CONTRIBUTING.md).
"""

from collections import defaultdict
from decimal import Decimal

from ledger.discounts import parse_code
from ledger.invoice import Invoice, LineItem

MONTHS = 12
INVOICES_PER_MONTH = 260_000
REGIONS = ("CA", "CA", "CA", "NY", "NY", "TX", "WA", "OR")
CODES = (
    (),
    (),
    (),
    ("SAVE10",),
    ("SAVE5",),
    ("SAVE15",),
    ("OFF5",),
    ("OFF10",),
    ("SAVE10", "OFF5"),
    ("SAVE20", "OFF10"),
    ("SAVE10", "SAVE5"),
    ("SAVE15", "SAVE10"),
    ("SAVE5", "SAVE20", "OFF5"),
    ("SAVE40", "OFF20"),
)
PARSED = {codes: [parse_code(code) for code in codes] for codes in CODES}


def sequence(seed):
    """A deterministic pseudo-random sequence: a linear congruential generator's high bits, 0 <= n < 2**23."""
    state = seed
    while True:
        state = (1103515245 * state + 12345) % 2**31
        yield state >> 8


def invoices_of(month):
    numbers = sequence(2025_00 + month)
    for n in range(INVOICES_PER_MONTH):
        lines = []
        for line in range(1 + next(numbers) % 4):
            cents = 99 + next(numbers) % 25_000
            lines.append(LineItem(f"S-{line}", "item", 1 + next(numbers) % 5, Decimal(cents) / 100))
        yield Invoice(
            f"INV-2025{month:02d}-{n:06d}",
            f"customer-{next(numbers) % 4000}",
            REGIONS[next(numbers) % len(REGIONS)],
            lines,
            PARSED[CODES[next(numbers) % len(CODES)]],
        )


# The filed FY2025 figures, month by month: invoices, subtotal, discount, tax, total.
FILED = {
    1: (260000, '237179494.66', '27192108.30', '10415154.47', '220402540.83'),
    2: (260000, '252914366.38', '30249942.55', '11413848.97', '234078272.80'),
    3: (260000, '236657761.47', '27220649.12', '10409720.41', '219846832.76'),
    4: (260000, '252564412.63', '30404062.57', '11377994.53', '233538344.59'),
    5: (260000, '237144595.53', '27228684.01', '10416346.50', '220332258.02'),
    6: (260000, '252728143.11', '30300632.46', '11399116.28', '233826626.93'),
    7: (260000, '237075697.15', '27174128.07', '10423504.32', '220325073.40'),
    8: (260000, '252702644.70', '30359911.65', '11393093.98', '233735827.03'),
    9: (260000, '236848910.85', '27101471.89', '10409590.04', '220157029.00'),
    10: (260000, '252281391.23', '30241452.43', '11380092.26', '233420031.06'),
    11: (260000, '236737827.31', '27121903.33', '10402246.06', '220018170.04'),
    12: (260000, '252575407.74', '30310052.79', '11391588.90', '233656943.85'),
}


def test_fy2025_totals_are_unchanged():
    replayed = {}
    for month in range(1, MONTHS + 1):
        sums = defaultdict(lambda: Decimal("0"))
        count = 0
        for invoice in invoices_of(month):
            count += 1
            sums["subtotal"] += invoice.subtotal()
            sums["discount"] += invoice.discount_total()
            sums["tax"] += invoice.tax()
            sums["total"] += invoice.total()
        replayed[month] = (count, str(sums["subtotal"]), str(sums["discount"]), str(sums["tax"]), str(sums["total"]))
    assert replayed == FILED
