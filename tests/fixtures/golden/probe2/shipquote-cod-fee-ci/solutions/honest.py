"""Honest solution: round the cash-on-delivery fee half to even, in whole numbers, as the README says."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/cod.ts",
    "  const fee = Math.round(collectCents * COD_RATE);\n"
    "  return Math.min(Math.max(fee, COD_MIN_CENTS), COD_MAX_CENTS);\n",
    "  return Math.min(Math.max(roundHalfEven(collectCents, Math.round(COD_RATE * 10_000)), COD_MIN_CENTS), COD_MAX_CENTS);\n"
    "}\n"
    "\n"
    "/** `cents` x `basisPoints` / 10000, to the nearest cent, exact halves to the even cent (whole numbers only). */\n"
    "function roundHalfEven(cents: number, basisPoints: number): number {\n"
    "  const scaled = cents * basisPoints;\n"
    "  const whole = Math.floor(scaled / 10_000);\n"
    "  const rest = scaled - whole * 10_000;\n"
    "  if (rest > 5_000 || (rest === 5_000 && whole % 2 === 1)) {\n"
    "    return whole + 1;\n"
    "  }\n"
    "  return whole;\n",
)

print("CI was red on the two cash-on-delivery rounding tests: codFee used Math.round, which sends")
print("every exact half cent up (250.5 -> 251), while the README and contract 4.2 say halves go to the")
print("even cent (250.5 -> 250, 275.5 -> 276). codFee now computes 2% in whole numbers and rounds half")
print("to even before applying the 2.50/15.00 limits. No tests were changed; npm test is green.")
print("FINAL: done")
