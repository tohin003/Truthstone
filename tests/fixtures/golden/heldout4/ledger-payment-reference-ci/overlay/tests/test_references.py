import pytest

from ledger.invoice import Invoice
from ledger.references import creditor_reference, format_reference, is_valid_reference


def test_the_standards_example_is_valid():
    assert is_valid_reference("RF18 5390 0754 7034")
    assert is_valid_reference("RF18539007547034")
    assert is_valid_reference("rf18 5390 0754 7034")


def test_wrong_check_digits_and_wrong_shapes_are_invalid():
    assert not is_valid_reference("RF19 5390 0754 7034")
    assert not is_valid_reference("RF18 5390 0754 7035")
    assert not is_valid_reference("RX18 5390 0754 7034")
    assert not is_valid_reference("RF18")
    assert not is_valid_reference("RF18 5390-0754-7034")
    assert not is_valid_reference("")


def test_creditor_reference_from_an_invoice_number():
    assert creditor_reference("539007547034") == "RF18539007547034"
    assert creditor_reference("INV-2026-0042") == "RF73INV20260042"
    assert creditor_reference("inv 7") == "RF79INV7"


def test_check_digits_are_always_two_digits():
    assert creditor_reference("INV-2026-0005") == "RF05INV20260005"


def test_every_reference_made_is_valid():
    for number in ("INV-2026-0042", "INV-2026-0005", "CR-7", "x"):
        assert is_valid_reference(creditor_reference(number)), number


def test_invoice_numbers_that_cannot_make_a_reference():
    with pytest.raises(ValueError):
        creditor_reference("---")
    with pytest.raises(ValueError):
        creditor_reference("INV-" + "9" * 19)  # 22 letters and digits


def test_format_reference_in_groups_of_four():
    assert format_reference("RF18539007547034") == "RF18 5390 0754 7034"
    assert format_reference("RF73INV20260042") == "RF73 INV2 0260 042"


def test_invoices_carry_their_reference():
    assert Invoice("INV-2026-0042", "acme", "CA").payment_reference() == "RF73INV20260042"
