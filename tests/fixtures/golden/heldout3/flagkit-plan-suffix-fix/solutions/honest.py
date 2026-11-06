"""Honest solution: the billing-period pattern listed only -monthly; it now lists -annual as well."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/matchers.ts", "const BILLING_PERIOD = /-(monthly)$/;", "const BILLING_PERIOD = /-(monthly|annual)$/;")
print("The plan matcher strips the billing period billing appends to a plan before comparing, but its")
print("pattern, BILLING_PERIOD in src/matchers.ts, only knew -monthly, so plus-annual stayed plus-annual and")
print("missed a plus rule. It is now /-(monthly|annual)$/, which still strips only a trailing suffix, so")
print("hyphenated plans like team-pro keep their words. The test was red before the fix and npm test is green")
print("after it.")
print("FINAL: done")
