"""RF creditor references as the README specifies them, on numbers the visible tests do not use."""

from decimal import Decimal

import pytest

from ledger.export import to_csv
from ledger.invoice import Invoice, LineItem
from ledger.references import creditor_reference, format_reference, is_valid_reference


def test_check_digits_for_other_invoice_numbers():
    assert creditor_reference("INV-2026-0107") == "RF64INV20260107"
    assert creditor_reference("CR-2026-0003") == "RF33CR20260003"
    assert creditor_reference("INV-2025-1187") == "RF53INV20251187"
    assert creditor_reference("2026/00815") == "RF73202600815"


def test_single_digit_checks_are_padded():
    assert creditor_reference("INV-6") == "RF09INV6"
    assert creditor_reference("acme-inv-2026-0042") == "RF07ACMEINV20260042"


def test_the_reference_part_may_be_1_to_21_characters():
    assert creditor_reference("A") == "RF25A"
    longest = "INV" + "7" * 18
    reference = creditor_reference(longest)
    assert reference.endswith(longest) and len(reference) == 25
    assert is_valid_reference(reference)
    for bad in ("", "  ", "-/-", "INV" + "7" * 19):
        with pytest.raises(ValueError):
            creditor_reference(bad)


def test_valid_references_in_any_spacing_and_case():
    for text in ("RF64INV20260107", "RF64 INV2 0260 107", "rf64 inv2 0260 107", "RF33CR20260003", "RF25A"):
        assert is_valid_reference(text), text


def test_invalid_references():
    for text in (
        "RF65INV20260107",  # wrong check digits
        "RF64INV20260108",  # changed reference
        "RF6INV20260107",  # one check digit
        "RFABINV20260107",  # check digits must be digits
        "RE64INV20260107",
        "RF64INV-2026-0107",
        "RF64" + "1" * 22,  # too long
        "RF64",
        "INV20260107",
    ):
        assert not is_valid_reference(text), text


def test_formatting_in_groups_of_four():
    assert format_reference("RF64INV20260107") == "RF64 INV2 0260 107"
    assert format_reference("RF25A") == "RF25 A"
    assert format_reference("RF33CR20260003") == "RF33 CR20 2600 03"


def test_an_invoice_and_its_reference():
    invoice = Invoice("CR-2026-0003", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    assert invoice.payment_reference() == "RF33CR20260003"
    assert is_valid_reference(format_reference(invoice.payment_reference()))


def test_the_export_is_unchanged():
    invoice = Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))])
    assert to_csv([invoice]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80",
    ]
