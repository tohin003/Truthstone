"""Due dates and overdue checks (README, "Due dates")."""

from datetime import date
from decimal import Decimal

from freezegun import freeze_time

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


def test_due_date_is_the_issue_date_plus_terms():
    assert invoice(date(2026, 3, 2)).due_date() == date(2026, 4, 1)
    assert invoice(date(2026, 10, 1), terms_days=14).due_date() == date(2026, 10, 15)


def test_a_weekend_due_date_moves_to_monday():
    assert invoice(date(2026, 8, 6)).due_date() == date(2026, 9, 7)  # Saturday -> Monday
    assert invoice(date(2026, 8, 7)).due_date() == date(2026, 9, 7)  # Sunday -> Monday


def test_overdue_only_after_the_due_date():
    unpaid = invoice(date(2026, 3, 2))  # due Wednesday 2026-04-01
    assert not unpaid.is_overdue(today=date(2026, 3, 31))
    assert not unpaid.is_overdue(today=date(2026, 4, 1))
    assert unpaid.is_overdue(today=date(2026, 4, 2))


def test_paid_invoices_are_never_overdue():
    assert not invoice(date(2026, 3, 2), paid=True).is_overdue(today=date(2026, 12, 31))


@freeze_time("2026-04-02")
def test_is_overdue_defaults_to_today():
    assert invoice(date(2026, 3, 2)).is_overdue()


@freeze_time("2026-04-01")
def test_not_overdue_on_the_due_date_itself():
    assert not invoice(date(2026, 3, 2)).is_overdue()
