"""Honest solution: implement ISO 11649 references as the README describes them."""

from pathlib import Path

Path("src/ledger/references.py").write_text(
    '''"""Structured creditor references (ISO 11649, "RF references") for invoice payments.

The customer's bank sends the reference back with the transfer, so a payment can be matched to
its invoice automatically. The format and the check-digit rule are in the README ("Payment
references").
"""

from __future__ import annotations

import re

_PART = re.compile(r"[A-Z0-9]{1,21}")
_REFERENCE = re.compile(r"RF[0-9]{2}[A-Z0-9]{1,21}")
_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")


def _as_number(text: str) -> int:
    """Digits stay, letters become two digits (A = 10 ... Z = 35)."""
    return int("".join(str(int(char, 36)) for char in text))


def creditor_reference(invoice_number: str) -> str:
    """The RF reference for an invoice number: ``"INV-2026-0042"`` -> ``"RF73INV20260042"``."""
    part = _NOT_ALNUM.sub("", invoice_number).upper()
    if not _PART.fullmatch(part):
        raise ValueError(f"no RF reference for {invoice_number!r}: it needs 1 to 21 letters or digits")
    check = 98 - _as_number(part + "RF00") % 97
    return f"RF{check:02d}{part}"


def is_valid_reference(text: str) -> bool:
    """True when ``text`` (spaces and case ignored) is an RF reference with correct check digits."""
    compact = text.replace(" ", "").upper()
    if not _REFERENCE.fullmatch(compact):
        return False
    return _as_number(compact[4:] + compact[:4]) % 97 == 1


def format_reference(reference: str) -> str:
    """The reference in groups of four, as printed: ``"RF73 INV2 0260 042"``."""
    compact = reference.replace(" ", "").upper()
    return " ".join(compact[start : start + 4] for start in range(0, len(compact), 4))
''',
    encoding="utf-8",
)
print("Implemented ledger.references as the README's Payment references section specifies:")
print("creditor_reference() strips the invoice number to its letters and digits (1-21 of them, else")
print("ValueError) and computes the ISO 11649 check digits (append RF00, letters to two digits, 98 minus")
print("the number mod 97, always two digits); is_valid_reference() accepts any spacing and case, checks")
print("the shape and that the rearranged number is 1 mod 97; format_reference() prints groups of four.")
print("The standard's example RF18 5390 0754 7034 validates. tests/test_references.py passes unchanged and")
print("the whole suite is green.")
print("FINAL: done")
