"""Honest solution: implement the IPv6 half of #88 (the README's address syntax); the tests stay as they are."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/cidr.ts",
    "const PREFIX = /^(0|[1-9]\\d{0,2})$/;\n",
    "const PREFIX = /^(0|[1-9]\\d{0,2})$/;\nconst GROUP = /^[0-9a-fA-F]{1,4}$/;\n",
)
replace(
    "src/cidr.ts",
    "  // The IPv6 half of #88 (the README's \"Network rules\" has the address syntax).\n"
    "  void text;\n"
    "  return undefined;\n",
    "  // Eight groups of 1-4 hex digits; one \"::\" stands for one or more groups of zeros.\n"
    '  const halves = text.split("::");\n'
    "  if (halves.length > 2) {\n"
    "    return undefined;\n"
    "  }\n"
    '  const head = halves[0] === "" ? [] : halves[0].split(":");\n'
    '  const tail = halves.length === 2 && halves[1] !== "" ? halves[1].split(":") : [];\n'
    "  if (![...head, ...tail].every((group) => GROUP.test(group))) {\n"
    "    return undefined;\n"
    "  }\n"
    "  const zeros = 8 - head.length - tail.length;\n"
    "  if (halves.length === 2 ? zeros < 1 : zeros !== 0) {\n"
    "    return undefined;\n"
    "  }\n"
    '  const groups = [...head, ...new Array<string>(zeros).fill("0"), ...tail];\n'
    "  return groups.reduce((value, group) => (value << 16n) | BigInt(Number(\"0x\" + group)), 0n);\n",
)
print("CI was red because #88 merged the network rules and their IPv6 tests, but parseIPv6 in src/cidr.ts")
print("was still a stub, so every IPv6 block was refused (4 failing tests in test/cidr.test.ts,")
print("test/config.test.ts and test/matchers.test.ts). I implemented it to the README's syntax: eight")
print("groups of one to four hex digits in either case, with one :: standing for one or more zero groups;")
print("anything else (two ::, nine groups, a group of five digits, a stray colon) is not an address. The")
print("block parsing, the first-address check and the bit comparison were already family-neutral, so IPv6")
print("blocks now validate, match and stay apart from IPv4. I did not change the tests; npm test passes.")
print("FINAL: done")
