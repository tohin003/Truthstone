"""Structured creditor references (ISO 11649, "RF references") for invoice payments.

The customer's bank sends the reference back with the transfer, so a payment can be matched to
its invoice automatically. The format and the check-digit rule are in the README ("Payment
references").
"""

from __future__ import annotations


def creditor_reference(invoice_number: str) -> str:
    """The RF reference for an invoice number: ``"INV-2026-0042"`` -> ``"RF73INV20260042"``."""
    raise NotImplementedError("RF references: the implementation follows #71")


def is_valid_reference(text: str) -> bool:
    """True when ``text`` (spaces and case ignored) is an RF reference with correct check digits."""
    raise NotImplementedError("RF references: the implementation follows #71")


def format_reference(reference: str) -> str:
    """The reference in groups of four, as printed: ``"RF73 INV2 0260 042"``."""
    raise NotImplementedError("RF references: the implementation follows #71")
