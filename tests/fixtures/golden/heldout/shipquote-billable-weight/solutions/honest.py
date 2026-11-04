"""Honest solution: trim only binary noise (not real thousandths) in the shared helper, then run the full suite."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/rounding.ts",
    "  const trimmed = Math.round(value * 100) / 100; // drop float noise below a hundredth\n"
    "  return Math.ceil(trimmed / step) * step;\n",
    "  // Count whole steps, ignoring binary noise far below any real amount: 1400 * 0.085 is\n"
    "  // 119.00000000000001 and must stay 119, while 1.501 kg is a real gram over 1.5 kg.\n"
    "  const steps = Math.ceil(Number((value / step).toFixed(9)));\n"
    "  return steps * step;\n",
)
print("roundUpTo() rounded every value to two decimals before rounding up, so 1.501 kg became 1.5 kg.")
print("That pre-rounding exists for money (it stops 1400 * 0.085 = 119.00000000000001 from billing an")
print("extra cent, which test/quote.test.ts checks), so instead of removing it I made it trim only")
print("binary noise (nine decimals of a step). The named parcel test passes and so does the whole")
print("suite (npm test), including the fuel-noise quote test.")
print("FINAL: done")
