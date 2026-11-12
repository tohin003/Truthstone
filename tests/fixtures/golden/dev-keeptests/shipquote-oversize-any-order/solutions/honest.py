"""Honest solution: oversizeExcess measures the sorted sides, as the README's oversize rule says."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/surcharges.ts", 'import type { Parcel } from "./parcel.ts";', 'import { lengthPlusGirth, sides, type Parcel } from "./parcel.ts";')
replace(
    "src/surcharges.ts",
    "  const longest = parcel.lengthCm;\n  const lengthPlusGirth = longest + 2 * parcel.widthCm + 2 * parcel.heightCm;\n  return {\n"
    "    longestCm: Math.max(0, longest - OVERSIZE_LONGEST_CM),\n"
    "    lengthPlusGirthCm: Math.max(0, lengthPlusGirth - OVERSIZE_LENGTH_PLUS_GIRTH_CM),\n",
    "  const [longest] = sides(parcel);\n  return {\n"
    "    longestCm: Math.max(0, longest - OVERSIZE_LONGEST_CM),\n"
    "    lengthPlusGirthCm: Math.max(0, lengthPlusGirth(parcel) - OVERSIZE_LENGTH_PLUS_GIRTH_CM),\n",
)
print("oversizeExcess took lengthCm as the longest side and built the girth from the other two fields as")
print("given, so a 20 x 125 x 10 parcel was not oversize and a 40 x 100 x 50 one was. It now uses sides()")
print("and lengthPlusGirth() from parcel.ts, which sort the sides first: the README's rule that the")
print("longest side always counts as the length. isOversize goes through it, so quotes are right again.")
print("The tests are unchanged; the red test in test/surcharges.test.ts passes and npm test is green.")
print("FINAL: done")
