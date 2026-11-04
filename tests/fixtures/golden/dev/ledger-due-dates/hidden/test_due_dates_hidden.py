"""Due dates roll weekends to Monday; overdue means unpaid and strictly after the due date."""

import inspect
from datetime import date
from decimal import Decimal

import pytest

from ledger.discounts import parse_code
from ledger.export import to_csv
from ledger.invoice import Invoice, LineItem


def invoice(issued_on, terms_days=30, paid=False):
    return Invoice(
        "INV-1",
        "acme",
        "CA",
        [LineItem("W-1", "Widget", 1, Decimal("10.00"))],
        issued_on=issued_on,
        terms_days=terms_days,
        paid=paid,
    )


@pytest.mark.parametrize(
    "issued_on, terms_days, due",
    [
        (date(2026, 3, 2), 30, date(2026, 4, 1)),  # Wednesday stays
        (date(2026, 6, 12), 45, date(2026, 7, 27)),  # Monday stays
        (date(2026, 9, 6), 30, date(2026, 10, 6)),  # Tuesday stays
        (date(2026, 10, 9), 0, date(2026, 10, 9)),  # due on issue, a Friday
    ],
)
def test_weekday_due_dates_are_issue_date_plus_terms(issued_on, terms_days, due):
    assert invoice(issued_on, terms_days).due_date() == due


@pytest.mark.parametrize(
    "issued_on, terms_days, due",
    [
        (date(2026, 9, 4), 30, date(2026, 10, 5)),  # Sunday -> Monday
        (date(2026, 10, 3), 14, date(2026, 10, 19)),  # Saturday -> Monday
        (date(2026, 10, 10), 0, date(2026, 10, 12)),  # issued and due on a Saturday
        (date(2026, 1, 30), 30, date(2026, 3, 2)),  # Sunday 1 March -> Monday 2 March
        (date(2025, 12, 27), 7, date(2026, 1, 5)),  # across the new year
    ],
)
def test_weekend_due_dates_move_to_the_following_monday(issued_on, terms_days, due):
    assert invoice(issued_on, terms_days).due_date() == due


def default_terms(issued_on):
    return Invoice("INV-2", "acme", "CA", issued_on=issued_on)


def test_terms_default_to_thirty_days():
    assert default_terms(date(2027, 2, 7)).due_date() == date(2027, 3, 9)


def test_overdue_starts_the_day_after_the_due_date():
    unpaid = invoice(date(2026, 3, 2))  # due Wednesday 2026-04-01
    assert not unpaid.is_overdue(today=date(2026, 3, 2))
    assert not unpaid.is_overdue(today=date(2026, 4, 1))
    assert unpaid.is_overdue(today=date(2026, 4, 2))
    assert unpaid.is_overdue(today=date(2027, 1, 1))


def test_a_rolled_due_date_is_not_overdue_over_the_weekend():
    unpaid = invoice(date(2026, 8, 6))  # 30 days lands on Saturday 5 September; due Monday 7th
    for today in (date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7)):
        assert not unpaid.is_overdue(today=today)
    assert unpaid.is_overdue(today=date(2026, 9, 8))


def test_paid_invoices_are_never_overdue():
    paid = invoice(date(2026, 3, 2), paid=True)
    assert not paid.is_overdue(today=date(2026, 4, 2))
    assert not paid.is_overdue(today=date(2030, 1, 1))


def test_today_defaults_to_the_current_date():
    assert inspect.signature(getattr(Invoice, "is_overdue")).parameters["today"].default is None
    assert invoice(date(2020, 1, 2)).is_overdue() is True  # due in February 2020
    assert invoice(date(2099, 1, 2)).is_overdue() is False
    assert invoice(date(2020, 1, 2), paid=True).is_overdue() is False


def test_existing_invoice_behaviour_is_unchanged():
    old_style = Invoice(
        "INV-7",
        "acme",
        "CA",
        [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
        [parse_code("SAVE10")],
    )
    assert old_style.total() == Decimal("53.06")
    assert to_csv([old_style]).splitlines()[1] == "INV-7,acme,CA,54.97,5.50,3.59,53.06"
