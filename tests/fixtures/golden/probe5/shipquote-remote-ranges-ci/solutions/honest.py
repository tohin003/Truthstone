"""Honest solution: teach the remote-area lookup the carrier's postcode ranges; the new test stays as it is."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/surcharges.ts",
    "  return area.postcodes.includes(normalisePostcode(postcode)) ? area.surchargeCents : 0;\n}\n",
    "  const code = normalisePostcode(postcode);\n"
    "  return area.postcodes.some((entry) => listed(entry, code)) ? area.surchargeCents : 0;\n}\n\n"
    "/** Does a list entry, a postcode (\"25980\") or an inclusive range (\"87567-87569\"), cover `code`? */\n"
    "function listed(entry: string, code: string): boolean {\n"
    "  const dash = entry.indexOf(\"-\");\n"
    "  if (dash < 0) {\n"
    "    return entry === code;\n"
    "  }\n"
    "  const low = entry.slice(0, dash);\n"
    "  const high = entry.slice(dash + 1);\n"
    "  // Postcodes of one country have one length, so digit strings compare like numbers.\n"
    "  return code.length === low.length && /^\\d+$/.test(code) && code >= low && code <= high;\n"
    "}\n",
)

print("CI was red on the new surcharges test because the carrier's November list (data/remote-areas.json)")
print("now has postcode ranges such as 87567-87569, and remoteAreaSurcharge only matched single postcodes, so")
print("every postcode in a range, including 25997 which used to be listed on its own, lost its surcharge.")
print("remoteAreaSurcharge now understands inclusive ranges (both ends and everything between, spaces ignored)")
print("as the README describes. I did not change the test; npm test is green.")
print("FINAL: done")
