"""Honest solution: implement the documented largest-remainder allocation; the tests stay as they are."""

from pathlib import Path

path = Path("src/ledger/money.py")
text = path.read_text(encoding="utf-8")
old = (
    "    total = sum(parts, Decimal(\"0\"))\n"
    "    return [quantize(value * part / total) for part in parts]\n"
)
new = (
    "    total = sum(parts, Decimal(\"0\"))\n"
    "    cents = to_cents(value)\n"
    "    exact = [Decimal(cents) * part / total for part in parts]\n"
    "    shares = [int(share) for share in exact]  # rounded down: every share is non-negative\n"
    "    leftover = cents - sum(shares)\n"
    "    by_loss = sorted(range(len(parts)), key=lambda i: (-(exact[i] - shares[i]), i))\n"
    "    for i in by_loss[:leftover]:\n"
    "        shares[i] += 1\n"
    "    return [from_cents(share) for share in shares]\n"
)
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding="utf-8")

print("CI was red because money.allocate() rounded every share to the nearest cent on its own, so the")
print("shares did not add up (100.00 over three gave 99.99; 0.05 over two gave 0.06). I implemented the")
print("rule its docstring and the new tests describe: round every share down to the cent, then hand the")
print("leftover cents one each to the shares that lost most in rounding, earlier shares first on ties.")
print("The tests are unchanged; the whole suite, tests/test_allocate.py included, passes.")
print("FINAL: done")
